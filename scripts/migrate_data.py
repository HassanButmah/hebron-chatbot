from dotenv import load_dotenv

load_dotenv()

import os
from typing import List, Type

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Set it in your .env file before running migration."
    )

from database import (  # noqa: E402
    Base,
    ChatMessage,
    ChatSession,
    FAQ,
    Feedback,
    FileRecord,
    ManualOverrides,
    SystemSettings,
    UnansweredQueries,
)


def migrate_orm_model(model: Type[Base], sqlite_session: Session, pg_session: Session) -> None:
    model_name = model.__name__
    print(f"Migrating {model_name}...")
    try:
        rows = sqlite_session.query(model).all()
    except Exception as exc:
        print(f"  Skipped {model_name} (SQLite source unavailable): {exc}")
        return

    for row in rows:
        sqlite_session.expunge(row)
        pg_session.merge(row)

    pg_session.commit()
    print(f"  Migrated {len(rows)} {model_name} row(s) successfully.")


def main() -> None:
    sqlite_engine = create_engine(
        "sqlite:///./rag_admin.db",
        connect_args={"check_same_thread": False},
    )
    pg_engine = create_engine(DATABASE_URL)

    SQLiteSession = sessionmaker(bind=sqlite_engine, autocommit=False, autoflush=False)
    PgSession = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)

    sqlite_session = SQLiteSession()
    pg_session = PgSession()

    # FK order: parents before children
    orm_models: List[Type[Base]] = [
        FileRecord,
        ChatSession,
        ChatMessage,
        Feedback,
        FAQ,
        ManualOverrides,
        SystemSettings,
        UnansweredQueries,
    ]

    try:
        print("Starting SQLite -> PostgreSQL ORM migration...")
        for model in orm_models:
            try:
                migrate_orm_model(model, sqlite_session, pg_session)
            except Exception as exc:
                pg_session.rollback()
                print(f"  Error migrating {model.__name__}: {exc}")
                raise
        print("Migration completed successfully.")
    except Exception as exc:
        pg_session.rollback()
        print(f"Migration failed: {exc}")
        raise
    finally:
        sqlite_session.close()
        pg_session.close()
        print("Closed database sessions.")


if __name__ == "__main__":
    main()
