"""
Dynamic ingestion service for Hebron University live data sources.

Responsibilities:
  1. Given a DynamicSource config, run the appropriate connector.
  2. Compare new records against the previous sync (via version_hash).
  3. Delete stale Chroma chunks for the source by stable source identifier.
  4. Embed and insert only changed / new documents.
  5. Record a DynamicSyncRun row with timing and counts.

Designed for Phase 1: manual sync triggered by the admin panel.
Scheduled sync (APScheduler) can be layered on top later.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from database import (
    SessionLocal,
    DynamicSyncRun,
    create_sync_run,
    finish_sync_run,
    get_dynamic_source,
    update_dynamic_source,
)
from src.connectors.official_api import get_connector

if TYPE_CHECKING:
    from src.rag_system import ArabicRAGChatbot

logger = logging.getLogger(__name__)


class DynamicIngestionService:
    """
    Orchestrates syncing a DynamicSource into the Chroma vector store.

    Requires a reference to the running ArabicRAGChatbot instance so it can
    call add_documents / delete_by_source without re-loading embeddings.
    """

    def __init__(self, chatbot: "ArabicRAGChatbot") -> None:
        self.chatbot = chatbot

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_source(self, source_id: int) -> Dict[str, Any]:
        """
        Sync a single DynamicSource by its DB id.

        Returns a summary dict suitable for a JSON API response:
          {ok, run_id, records_fetched, records_changed, chunks_updated, error}
        """
        source_config = get_dynamic_source(source_id)
        if source_config is None:
            return {"ok": False, "error": f"DynamicSource id={source_id} not found"}

        if not source_config.get("is_enabled"):
            return {"ok": False, "error": "Source is disabled"}

        # Mark source as syncing and clear any previous error message
        update_dynamic_source(source_id, status="syncing", error_message="")

        run_id = create_sync_run(source_id)
        if run_id is None:
            update_dynamic_source(source_id, status="error", error_message="Could not create sync run row")
            return {"ok": False, "error": "Could not create sync run row"}

        try:
            result = self._do_sync(source_config, run_id)
        except Exception as exc:
            logger.exception("Unexpected error during sync for source_id=%s", source_id)
            err = str(exc)
            finish_sync_run(run_id, "error", error_message=err)
            update_dynamic_source(source_id, status="error", error_message=err)
            return {"ok": False, "run_id": run_id, "error": err}

        # Update source status
        if result.get("error"):
            update_dynamic_source(
                source_id,
                status="error",
                error_message=result["error"],
                last_sync_at=datetime.utcnow(),
            )
        else:
            update_dynamic_source(
                source_id,
                status="ok",
                error_message="",
                last_sync_at=datetime.utcnow(),
            )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_sync(self, source_config: Dict[str, Any], run_id: int) -> Dict[str, Any]:
        source_id = source_config["id"]

        connector = get_connector(source_config)
        if connector is None:
            err = f"No connector registered for source_type='{source_config.get('source_type')}'"
            finish_sync_run(run_id, "error", error_message=err)
            return {"ok": False, "run_id": run_id, "error": err}

        connector_result = connector.run()

        if not connector_result.available:
            # Source not configured — not an error, just inform the admin
            finish_sync_run(run_id, "skipped", error_message=connector_result.error)
            return {
                "ok": False,
                "run_id": run_id,
                "error": connector_result.error,
                "records_fetched": 0,
                "records_changed": 0,
                "chunks_updated": 0,
            }

        if connector_result.error:
            finish_sync_run(run_id, "error", error_message=connector_result.error)
            return {"ok": False, "run_id": run_id, "error": connector_result.error}

        # ------------------------------------------------------------------
        # Change detection: compare version_hash per record against
        # what is currently indexed in Chroma.  We read the current hashes
        # from Chroma metadata so we don't need a separate cache table.
        # ------------------------------------------------------------------
        chroma_source_key = f"dynamic_{source_config['source_type']}_{source_id}"
        existing_hashes = self._get_existing_hashes(chroma_source_key)

        new_records = connector_result.records
        new_docs = connector_result.documents

        new_hash_set = {rec.get("version_hash", "") for rec in new_records}

        # Compare both directions:
        # - new records not yet in Chroma  (additions / updates)
        # - old Chroma records not in new API response  (removals)
        # If the sets are identical, nothing changed and we skip re-indexing.
        any_change = new_hash_set != existing_hashes
        records_changed = len(new_hash_set - existing_hashes)  # added/updated count

        chunks_updated = 0
        if any_change:
            # Replace all chunks for this source atomically:
            # delete everything, then re-insert exactly what the API returned now.
            # This guarantees Chroma always mirrors the current API state —
            # including removals of events that are no longer in the response.
            self._delete_source_chunks(chroma_source_key)
            chunks_updated = self._index_documents(new_docs)
        else:
            logger.info(
                "Sync source_id=%s: all %d records unchanged — skipping re-index",
                source_id, len(new_records),
            )

        finish_sync_run(
            run_id,
            "success",
            records_fetched=len(new_records),
            records_changed=records_changed,
            chunks_updated=chunks_updated,
        )
        return {
            "ok": True,
            "run_id": run_id,
            "records_fetched": len(new_records),
            "records_changed": records_changed,
            "chunks_updated": chunks_updated,
        }

    def _get_existing_hashes(self, chroma_source_key: str) -> set:
        """
        Retrieve version_hash values currently stored in Chroma for this source.
        Returns an empty set when no chunks exist or the vector store is not loaded.
        """
        vs = self.chatbot.vectorstore
        if vs is None:
            return set()
        try:
            result = vs._collection.get(
                where={"source": {"$eq": chroma_source_key}},
                include=["metadatas"],
                limit=100_000,
            )
            metadatas = result.get("metadatas") or []
            return {m.get("version_hash", "") for m in metadatas if m.get("version_hash")}
        except Exception as exc:
            logger.warning("Could not query existing hashes from Chroma: %s", exc)
            return set()

    def _delete_source_chunks(self, chroma_source_key: str) -> None:
        """Remove all Chroma chunks whose metadata 'source' matches the key."""
        vs = self.chatbot.vectorstore
        if vs is None:
            return
        try:
            with self.chatbot._lock:
                vs._collection.delete(where={"source": {"$eq": chroma_source_key}})
                vs.persist()
            logger.info("Deleted Chroma chunks for source=%r", chroma_source_key)
        except Exception as exc:
            logger.warning("_delete_source_chunks failed for %r: %s", chroma_source_key, exc)

    def _index_documents(self, docs) -> int:
        """Add documents to Chroma and return the count of chunks inserted."""
        if not docs:
            return 0
        try:
            with self.chatbot._lock:
                if self.chatbot.vectorstore is None:
                    from langchain_community.vectorstores import Chroma
                    self.chatbot.vectorstore = Chroma.from_documents(
                        documents=docs,
                        embedding=self.chatbot.embeddings,
                        persist_directory=self.chatbot.persist_dir,
                    )
                else:
                    self.chatbot.vectorstore.add_documents(docs)
                self.chatbot.vectorstore.persist()
            logger.info("Indexed %d dynamic documents into Chroma", len(docs))
            return len(docs)
        except Exception as exc:
            logger.error("_index_documents failed: %s", exc)
            raise
