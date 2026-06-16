"""
Reset PostgreSQL SERIAL/IDENTITY sequences to match MAX(id) after SQLite migration.

Requires DATABASE_URL (same as database.py). Safe to re-run; idempotent for a given dataset.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import inspect, text

load_dotenv()

from database import Base, engine  # noqa: E402


def reset_id_sequence(conn, schema: str, table_name: str) -> None:
    regclass = f"{schema}.{table_name}"
    qualified = f'"{schema}"."{table_name}"'
    try:
        # Third arg is_called: false when table is empty so the next insert gets id=1;
        # true when rows exist so the next nextval is MAX(id)+1.
        sql = text(
            f"""
            SELECT setval(
                pg_get_serial_sequence(:regclass, 'id'),
                COALESCE((SELECT MAX(id) FROM {qualified}), 1),
                COALESCE((SELECT (MAX(id) IS NOT NULL) FROM {qualified}), false)
            )
            """
        )
        conn.execute(sql, {"regclass": regclass})
        conn.commit()
        print(f"Updated sequence for {table_name}.id successfully.")
    except Exception as exc:
        conn.rollback()
        print(f"Skipped {regclass} (no serial on id or not applicable): {exc}")


def main() -> None:
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print("DATABASE_URL is not set; database.py should have failed on import.")
        return

    base_tables = {(t.schema or "public", t.name) for t in Base.metadata.tables.values()}

    print("Fixing PostgreSQL sequences for tables in Base.metadata (with id + serial)...")

    with engine.connect() as conn:
        for _table_key, table in Base.metadata.tables.items():
            if "id" not in table.c:
                continue
            schema = table.schema or "public"
            reset_id_sequence(conn, schema, table.name)

        print("Fixing sequences for other public tables with an id column...")
        inspector = inspect(engine)
        for tbl in inspector.get_table_names(schema="public"):
            if ("public", tbl) in base_tables:
                continue
            cols = inspector.get_columns(tbl, schema="public")
            if not any(c.get("name") == "id" for c in cols):
                continue
            reset_id_sequence(conn, "public", tbl)

    print("Done.")


if __name__ == "__main__":
    main()
