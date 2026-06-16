"""
Hebron RAG — Ghost Chunk Cleanup Tool
======================================
Finds and optionally removes Chroma vector chunks that no longer have a
matching record in PostgreSQL (orphaned / "ghost" chunks).

Two sources of ghost chunks:
  1. Static files  — chunks whose 'source' metadata value (the bare filename)
                     does not match any active FileRecord in the database.
  2. Dynamic data  — chunks whose 'source' starts with "dynamic_" but the
                     corresponding DynamicSource row no longer exists in the DB.

Usage:
    # Preview only — show what would be deleted (safe, no changes made)
    conda activate arabic-rag
    python cleanup_ghost_chunks.py

    # Actually delete the ghost chunks
    python cleanup_ghost_chunks.py --delete

    # Limit to a specific source key (useful for targeted cleanup)
    python cleanup_ghost_chunks.py --delete --source "dynamic_calendar_3"
"""
import argparse
import os
import sys
from pathlib import Path

# ── Project setup ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from database import SessionLocal, FileRecord, DynamicSource


# ── Resolve Chroma persist dir (same logic as rag_api.py) ────────────────────
def _resolve_persist_dir() -> str:
    raw = (os.getenv("PERSIST_DIR") or "").strip()
    if not raw:
        return str(PROJECT_ROOT / "chroma_db")
    return raw if os.path.isabs(raw) else str((PROJECT_ROOT / raw).resolve())


# ── Load known-good source keys from PostgreSQL ───────────────────────────────
def _get_known_sources() -> tuple[set[str], set[str]]:
    """
    Returns:
      file_sources    — set of filenames for active FileRecords
      dynamic_sources — set of "dynamic_{type}_{id}" keys for active DynamicSources
    """
    db = SessionLocal()
    try:
        file_sources = {
            row.filename
            for row in db.query(FileRecord.filename)
                          .filter(FileRecord.status != "retired")
                          .all()
        }
        dynamic_sources = {
            f"dynamic_{row.source_type}_{row.id}"
            for row in db.query(DynamicSource.id, DynamicSource.source_type).all()
        }
    finally:
        db.close()

    return file_sources, dynamic_sources


# ── Chroma helpers ────────────────────────────────────────────────────────────
def _open_chroma(persist_dir: str):
    """Open the Chroma collection directly (no Ollama / embeddings needed)."""
    try:
        import chromadb
    except ImportError:
        print("ERROR: chromadb is not installed. Run: pip install chromadb")
        sys.exit(1)

    if not os.path.isdir(persist_dir):
        print(f"ERROR: Chroma persist directory not found: {persist_dir!r}")
        print("       The chatbot may never have indexed any documents.")
        sys.exit(1)

    client = chromadb.PersistentClient(path=persist_dir)

    # LangChain uses the collection named "langchain" by default
    try:
        collection = client.get_collection("langchain")
    except Exception:
        # Fallback: list all collections and pick the first one
        cols = client.list_collections()
        if not cols:
            print("No collections found in the Chroma database. Nothing to clean up.")
            sys.exit(0)
        collection = client.get_collection(cols[0].name)
        print(f"  (Using collection: {cols[0].name!r})")

    return collection


def _get_all_sources(collection) -> dict[str, list[str]]:
    """
    Return {source_value: [chunk_id, ...]} for every chunk in the collection.
    Uses pagination because Chroma limits single-get results.
    """
    source_to_ids: dict[str, list[str]] = {}
    offset = 0
    batch = 10_000

    while True:
        result = collection.get(
            include=["metadatas"],
            limit=batch,
            offset=offset,
        )
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []

        if not ids:
            break

        for chunk_id, meta in zip(ids, metadatas):
            source = (meta or {}).get("source", "")
            source_to_ids.setdefault(source, []).append(chunk_id)

        if len(ids) < batch:
            break
        offset += batch

    return source_to_ids


def _delete_by_ids(collection, ids: list[str], batch_size: int = 5_000) -> int:
    """Delete chunks in batches. Returns total deleted count."""
    deleted = 0
    for i in range(0, len(ids), batch_size):
        batch = ids[i : i + batch_size]
        collection.delete(ids=batch)
        deleted += len(batch)
    return deleted


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Find and optionally remove ghost Chroma chunks."
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete the ghost chunks (default: dry-run preview only).",
    )
    parser.add_argument(
        "--source",
        metavar="KEY",
        default=None,
        help="Only check/delete this specific source key (e.g. 'dynamic_calendar_3').",
    )
    args = parser.parse_args()

    persist_dir = _resolve_persist_dir()

    print("=" * 64)
    print("  Hebron RAG — Ghost Chunk Cleanup")
    print("=" * 64)
    print(f"  Chroma path : {persist_dir}")
    print(f"  Mode        : {'DELETE' if args.delete else 'DRY-RUN (preview only)'}")
    if args.source:
        print(f"  Filter      : source = {args.source!r}")
    print()

    # 1. Known-good sources from PostgreSQL
    print("[1/4] Loading known sources from PostgreSQL …")
    file_sources, dynamic_sources = _get_known_sources()
    known = file_sources | dynamic_sources
    print(f"      {len(file_sources)} active file(s), {len(dynamic_sources)} active dynamic source(s)")
    print(f"      {len(known)} total known source keys")
    print()

    # 2. Open Chroma
    print("[2/4] Opening Chroma database …")
    collection = _open_chroma(persist_dir)
    print(f"      Collection total items: {collection.count()}")
    print()

    # 3. Enumerate all sources in Chroma
    print("[3/4] Scanning Chroma for ghost chunks …")
    source_to_ids = _get_all_sources(collection)
    print(f"      Found {len(source_to_ids)} distinct source key(s) in Chroma")
    print()

    # Apply --source filter if requested
    if args.source:
        source_to_ids = {k: v for k, v in source_to_ids.items() if k == args.source}
        if not source_to_ids:
            print(f"  Source key {args.source!r} not found in Chroma. Nothing to do.")
            return

    # 4. Identify ghost sources
    ghost_sources = {src: ids for src, ids in source_to_ids.items() if src not in known}

    print("[4/4] Results")
    print("-" * 64)

    if not ghost_sources:
        print("  ✅ No ghost chunks found. Chroma is clean.")
        print()
        _print_summary_table(source_to_ids, known)
        return

    total_ghost_chunks = sum(len(ids) for ids in ghost_sources.values())
    print(f"  Found {len(ghost_sources)} ghost source(s) — {total_ghost_chunks} orphaned chunk(s):\n")

    for src, ids in sorted(ghost_sources.items()):
        category = _classify(src)
        print(f"  ⚠  [{category}]  {src!r}  ({len(ids)} chunk(s))")

    print()

    if not args.delete:
        print("  ℹ  Dry-run: no changes made.")
        print("     Re-run with --delete to permanently remove these chunks.")
        print()
        _print_summary_table(source_to_ids, known)
        return

    # ── Delete ────────────────────────────────────────────────────────────────
    print("  Deleting ghost chunks …\n")
    total_deleted = 0
    for src, ids in sorted(ghost_sources.items()):
        deleted = _delete_by_ids(collection, ids)
        total_deleted += deleted
        print(f"  ✅ Deleted {deleted} chunk(s) for source {src!r}")

    print()
    print(f"  Removed {total_deleted} ghost chunk(s) from Chroma.")
    print()
    print(f"  Chroma collection now has {collection.count()} chunk(s) total.")

    print()
    _print_summary_table(source_to_ids, known, after_delete=True,
                         deleted_sources=set(ghost_sources.keys()))


def _classify(source_key: str) -> str:
    """Human-readable category for display."""
    if source_key.startswith("dynamic_"):
        return "dynamic source"
    if source_key == "":
        return "no source metadata"
    return "uploaded file"


def _print_summary_table(
    source_to_ids: dict,
    known: set,
    after_delete: bool = False,
    deleted_sources: set | None = None,
):
    deleted_sources = deleted_sources or set()
    print("  Source inventory (from Chroma):")
    print(f"  {'Source key':<52} {'Chunks':>6}  Status")
    print("  " + "-" * 64)
    for src, ids in sorted(source_to_ids.items()):
        if src in deleted_sources:
            status = "🗑  deleted"
        elif src in known:
            status = "✅ active"
        else:
            status = "⚠  ghost" + (" — not deleted (dry-run)" if not after_delete else "")
        display = src if len(src) <= 50 else src[:47] + "..."
        print(f"  {display:<52} {len(ids):>6}  {status}")
    print()


if __name__ == "__main__":
    main()
