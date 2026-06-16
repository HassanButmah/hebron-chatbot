"""
Persistent storage for RAG Admin: PostgreSQL + SQLAlchemy.
Ensures the uploads/ directory exists at project root.
"""
import logging
import os
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Float, Boolean, func, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

_uploads_env = (os.getenv("RAG_UPLOADS_DIR") or "").strip()
if _uploads_env:
    UPLOADS_DIR = _uploads_env if os.path.isabs(_uploads_env) else os.path.join(BASE_DIR, _uploads_env)
else:
    UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOADS_DIR, exist_ok=True)

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add a PostgreSQL connection string to your environment or .env file."
    )

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

DEFAULT_SETTINGS = {
    "ar_system_prompt": (
        "أنت مساعد ذكي ولطيف وممثل رسمي لجامعة الخليل (Hebron University).\n"
        "مهمتك هي الإجابة على استفسارات الطلاب والزوار بناءً على 'السياق' المقدم فقط.\n\n"
        "قواعد هامة:\n"
        "1. لا تقم بتأليف أو اختراع أي معلومات من خارج السياق.\n"
        "2. استخدم النقاط المرتبة (Bullet points) لتسهيل قراءة المعلومات.\n"
        "3. حافظ على نبرة احترافية، مرحبة، وأكاديمية.\n"
        "4. لا تذكر كلمات مثل \"السياق\" أو \"المستندات\" في الإجابة.\n"
        "5. أجب دائماً باللغة العربية عندما يكون سؤال المستخدم بالعربية.\n"
        "6. إذا وجدت في السياق بيانات حية (تقويم، إعلانات، مواعيد تسجيل)، فاذكر "
        "التواريخ والمعلومات ذات الصلة بوضوح.\n"
        "7. عند ذكر روابط من السياق: اكتب تسمية قصيرة ثم نقطتين ثم الرابط كنص عادي يبدأ "
        "بـ https:// أو http://. لا تستخدم أبداً صيغة ماركداون [نص](رابط) لأنها تفسد الروابط "
        "في واجهات الدردشة.\n\n"
        "تنسيق الإجابة:\n"
        "- ابدأ بجملة أو جملتين مختصرتين تلخصان الجواب مباشرة.\n"
        "- اجعل الفقرات قصيرة وتجنب الحشو."
    ),
    "en_system_prompt": (
        "You are a helpful, friendly official representative of Hebron University.\n"
        "Your task is to answer questions based ONLY on the 'context' provided.\n\n"
        "Important Rules:\n"
        "1. Do not hallucinate or invent information outside the context.\n"
        "2. Use bullet points for readability.\n"
        "3. Maintain a professional and welcoming academic tone.\n"
        "4. Do not use words like \"context\" or \"documents\" in your answer.\n"
        "5. Always answer in English when the user's question is in English.\n"
        "6. If the context includes live data (calendar events, announcements, "
        "registration deadlines), state the relevant dates and details clearly.\n"
        "7. For URLs from context: write a short label, a colon, a space, then the raw URL "
        "(https:// or http://). Never use Markdown links [text](url) — they break chat widgets "
        "and RTL layouts.\n\n"
        "Formatting:\n"
        "- Start with a brief direct answer.\n"
        "- Keep paragraphs short and avoid fluff."
    ),
    "ar_dont_know": "عذراً، لا أملك معلومات دقيقة حول هذا في الوقت الحالي، يمكنك التواصل مع إدارة الجامعة أو زيارة الموقع الرسمي.",
    "en_dont_know": "Sorry, I don't have enough information to answer this question. Please contact the university administration or visit the official Hebron University website.",
    "ar_low_conf": "عذراً، لم أتمكن من العثور على معلومات دقيقة حول هذا الموضوع في قاعدة بيانات الجامعة. يرجى التواصل مع عمادة القبول والتسجيل أو زيارة الموقع الرسمي لجامعة الخليل للحصول على المساعدة.",
    "en_low_conf": "Sorry, I couldn't find exact information about this topic in the university database. Please contact the Deanship of Admission and Registration or visit the official Hebron University website for assistance.",
    "lang_not_supported": (
        "عذراً، لا أستطيع الردّ إلا باللغتين العربية والإنجليزية.\n"
        "Sorry, I can only respond in Arabic or English."
    ),
    "ar_out_of_scope": (
        "أنا مساعد جامعة الخليل المتخصص، ويسعدني الإجابة على أسئلتك المتعلقة "
        "بجامعة الخليل فقط، مثل: القبول والتسجيل، الكليات والأقسام، الرسوم "
        "الدراسية، التقويم الأكاديمي، وغيرها. هل لديك سؤال عن جامعة الخليل؟"
    ),
    "en_out_of_scope": (
        "I'm the Hebron University assistant, specialized in answering questions "
        "about Hebron University only — such as admissions, registration, colleges, "
        "tuition, academic calendar, and more. "
        "Is there anything I can help you with regarding Hebron University?"
    ),
}


class FileRecord(Base):
    __tablename__ = "file_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Stored name on disk and in Chroma (unique, safe for paths and URLs)
    filename = Column(String(512), unique=True, nullable=False)
    file_path = Column(String(1024), nullable=False)
    # Original name as uploaded (for display; can be Arabic or any name)
    original_filename = Column(String(512), nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    chunk_count = Column(Integer, nullable=False)

    # --- Document freshness / lifecycle fields ---
    # URL of the source document (university website, shared drive, etc.)
    source_url = Column(String(2048), nullable=True)
    # Person/department responsible for keeping this document current
    owner = Column(String(256), nullable=True)
    # Free-text category: 'academic', 'admission', 'calendar', etc.
    category = Column(String(128), nullable=True)
    # Date from which this document's content is valid
    valid_from = Column(DateTime, nullable=True)
    # Date after which this document should be considered outdated
    valid_until = Column(DateTime, nullable=True)
    # Timestamps for the review workflow
    last_reviewed_at = Column(DateTime, nullable=True)
    next_review_at = Column(DateTime, nullable=True)
    # SHA-256 hex digest of the file contents for change detection
    content_hash = Column(String(64), nullable=True)
    # Lifecycle status: 'active' | 'stale' | 'retired'
    status = Column(String(32), nullable=False, server_default="active")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id = Column(String(256), primary_key=True)
    user_id = Column(String(256), nullable=True)  # Group sessions by user/browser
    title = Column(String(512), nullable=True)   # Short title; default "New Chat" when created
    start_time = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(256), ForeignKey("chat_sessions.session_id"), nullable=False)
    role = Column(String(32), nullable=False)  # 'user' or 'bot'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    generation_time = Column(Float, nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False)
    rating = Column(String(32), nullable=False)  # 'like' or 'dislike'
    timestamp = Column(DateTime, default=datetime.utcnow)


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    question_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ManualOverrides(Base):
    __tablename__ = "manual_overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger_phrase = Column(Text, unique=True, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemSettings(Base):
    __tablename__ = "system_settings"

    key = Column(String(256), primary_key=True)
    value = Column(Text, nullable=True)


class UnansweredQueries(Base):
    __tablename__ = "unanswered_queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=True)
    reason = Column(Text, nullable=True, default="غير معروف")
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String(32), nullable=True, default="pending")


class AdminUser(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="superadmin")


# =============================================================================
# Document version / audit trail
# =============================================================================

class DocumentVersion(Base):
    """Audit trail: one row for each upload, replace, review, or retire event on a FileRecord."""
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_record_id = Column(Integer, ForeignKey("file_records.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False, default=1)
    # Snapshot of filename / path at the time of this version
    filename = Column(String(512), nullable=False)
    original_filename = Column(String(512), nullable=True)
    file_path = Column(String(1024), nullable=False)
    chunk_count = Column(Integer, nullable=False, default=0)
    content_hash = Column(String(64), nullable=True)
    # Action that created this version entry
    action = Column(String(64), nullable=False)  # 'uploaded' | 'replaced' | 'reviewed' | 'retired'
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# =============================================================================
# Dynamic sources
# =============================================================================

class DynamicSource(Base):
    """
    Configuration record for a live university data source (API endpoint).
    One row per logical source, e.g. the calendar API or announcements feed.
    """
    __tablename__ = "dynamic_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    # Logical type used by connectors: 'calendar' | 'announcements' | 'admissions' | 'generic'
    source_type = Column(String(64), nullable=False)
    # Base URL of the official university API. NULL means not configured yet.
    endpoint_url = Column(String(2048), nullable=True)
    # Legacy frequency label — kept for backward compat; scheduling is now driven by
    # schedule_type + sync_times + schedule_day / schedule_month_day.
    sync_frequency = Column(String(32), nullable=False, server_default="manual")
    # Scheduling fields (Phase 2 — APScheduler auto-sync)
    # 'manual' | 'daily' | 'weekly' | 'monthly'
    schedule_type = Column(String(32), nullable=False, server_default="manual")
    # Comma-separated HH:MM times in 24-h format, e.g. "06:00,13:00,21:00"
    sync_times = Column(String(256), nullable=True)
    # Weekly: comma-separated APScheduler day_of_week values, e.g. "0,2,4" (Mon=0, Sun=6)
    schedule_day = Column(String(64), nullable=True)
    # Monthly: comma-separated day-of-month values, e.g. "1,15"
    schedule_month_day = Column(String(64), nullable=True)
    is_enabled = Column(Boolean, nullable=False, server_default="true")
    last_sync_at = Column(DateTime, nullable=True)
    # Current operational status
    # 'not_configured' | 'ok' | 'error' | 'syncing'
    status = Column(String(32), nullable=False, server_default="not_configured")
    error_message = Column(Text, nullable=True)
    # Optional: auth token / API key stored in DB (prefer env vars in production)
    auth_token = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DynamicSyncRun(Base):
    """
    One row per sync attempt for a DynamicSource.
    Tracks timing, record counts, and any error details.
    """
    __tablename__ = "dynamic_sync_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("dynamic_sources.id", ondelete="CASCADE"), nullable=False)
    # 'running' | 'success' | 'error' | 'skipped'
    status = Column(String(32), nullable=False, server_default="running")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    records_fetched = Column(Integer, nullable=False, default=0)
    records_changed = Column(Integer, nullable=False, default=0)
    chunks_updated = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)


def create_default_admin(session: Session) -> None:
    """If no admins exist, seed the default superadmin account."""
    if session.query(AdminUser).first() is not None:
        return
    session.add(
        AdminUser(
            username="ChatBot",
            password_hash=generate_password_hash("Hebron@uni"),
            role="superadmin",
        )
    )
    session.commit()


def verify_admin_login(session: Session, username: str, password: str) -> Optional[AdminUser]:
    """Return the AdminUser if credentials match, else None."""
    user = session.query(AdminUser).filter(AdminUser.username == username).first()
    if user is None:
        return None
    if check_password_hash(user.password_hash, password):
        return user
    return None


def delete_session(session_id: str) -> Tuple[bool, Optional[str]]:
    """
    Delete a chat session and all its messages and related feedback rows.
    Returns (True, None) on success, or (False, error_message) on failure.
    """
    db = SessionLocal()
    try:
        sess = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if not sess:
            return False, "Session not found"
        msg_ids = [m.id for m in db.query(ChatMessage).filter(ChatMessage.session_id == session_id).all()]
        if msg_ids:
            db.query(Feedback).filter(Feedback.message_id.in_(msg_ids)).delete(synchronize_session=False)
        db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete(synchronize_session=False)
        db.delete(sess)
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def count_distinct_chat_users() -> int:
    """Distinct non-empty user_id values on chat_sessions (proxy for 'active users')."""
    db = SessionLocal()
    try:
        n = (
            db.query(func.count(func.distinct(ChatSession.user_id)))
            .filter(
                ChatSession.user_id.isnot(None),
                ChatSession.user_id != "",
            )
            .scalar()
        )
        return int(n or 0)
    finally:
        db.close()


def _migrate_existing_tables() -> None:
    """
    Safely add new columns to pre-existing tables using ADD COLUMN IF NOT EXISTS.
    PostgreSQL 9.6+ supports IF NOT EXISTS in ALTER TABLE.
    This is a lightweight alternative to Alembic for student-project scope.
    """
    new_file_record_columns = [
        ("source_url",       "VARCHAR(2048)"),
        ("owner",            "VARCHAR(256)"),
        ("category",         "VARCHAR(128)"),
        ("valid_from",       "TIMESTAMP WITHOUT TIME ZONE"),
        ("valid_until",      "TIMESTAMP WITHOUT TIME ZONE"),
        ("last_reviewed_at", "TIMESTAMP WITHOUT TIME ZONE"),
        ("next_review_at",   "TIMESTAMP WITHOUT TIME ZONE"),
        ("content_hash",     "VARCHAR(64)"),
        ("status",           "VARCHAR(32) NOT NULL DEFAULT 'active'"),
    ]
    new_dynamic_source_columns = [
        ("schedule_type",    "VARCHAR(32) NOT NULL DEFAULT 'manual'"),
        ("sync_times",       "VARCHAR(256)"),
        ("schedule_day",     "VARCHAR(64)"),
        ("schedule_month_day", "VARCHAR(64)"),
    ]
    with engine.connect() as conn:
        for col_name, col_type in new_file_record_columns:
            try:
                conn.execute(
                    text(f"ALTER TABLE file_records ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                )
            except Exception as exc:
                logger.warning("Migration: could not add column %s to file_records: %s", col_name, exc)
        for col_name, col_type in new_dynamic_source_columns:
            try:
                conn.execute(
                    text(f"ALTER TABLE dynamic_sources ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                )
            except Exception as exc:
                logger.warning("Migration: could not add column %s to dynamic_sources: %s", col_name, exc)
        conn.commit()


def init_db():
    """Create all tables, run lightweight migrations, and ensure uploads directory exists."""
    Base.metadata.create_all(bind=engine)
    _migrate_existing_tables()
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    db = SessionLocal()
    try:
        create_default_admin(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_setting(key: str) -> str:
    """Fetch system setting from DB, fallback to DEFAULT_SETTINGS."""
    db = SessionLocal()
    try:
        row = db.query(SystemSettings).filter(SystemSettings.key == key).first()
        if row and row.value is not None:
            return str(row.value)
        return DEFAULT_SETTINGS.get(key, "")
    except Exception:
        return DEFAULT_SETTINGS.get(key, "")
    finally:
        db.close()


# ── LLM provider configuration ────────────────────────────────────────────────
# Stored in the SystemSettings table under these keys.
# DB values take priority over .env so admin-panel changes apply without restart.
# NOTE: api_key is stored as plain text. Encrypt at rest in a production deployment.

_LLM_CONFIG_KEYS = ("llm_provider", "llm_api_base_url", "llm_api_key", "llm_model_name")
_LLM_DEFAULTS = {
    "llm_provider":     "openai_compatible",
    "llm_api_base_url": "https://api.deepseek.com",
    "llm_api_key":      "",
    "llm_model_name":   "deepseek-chat",
}


def get_llm_config() -> Dict[str, str]:
    """
    Return the current LLM configuration from the DB.
    Falls back to _LLM_DEFAULTS for any key not yet stored.
    """
    db = SessionLocal()
    try:
        rows = db.query(SystemSettings).filter(
            SystemSettings.key.in_(_LLM_CONFIG_KEYS)
        ).all()
        result = dict(_LLM_DEFAULTS)
        for row in rows:
            if row.value is not None:
                result[row.key] = str(row.value)
        return result
    except Exception as exc:
        logger.warning("get_llm_config DB error: %s", exc)
        return dict(_LLM_DEFAULTS)
    finally:
        db.close()


def save_llm_config(
    provider: str,
    api_base_url: str,
    api_key: str,
    model_name: str,
) -> bool:
    """
    Persist LLM configuration to the DB.
    Pass an empty string for api_key to leave the stored key unchanged.
    """
    db = SessionLocal()
    try:
        updates = {
            "llm_provider":     provider.strip(),
            "llm_api_base_url": api_base_url.strip(),
            "llm_model_name":   model_name.strip(),
        }
        # Only update the key if the caller actually supplied one
        if api_key.strip():
            updates["llm_api_key"] = api_key.strip()

        for key, value in updates.items():
            row = db.query(SystemSettings).filter(SystemSettings.key == key).first()
            if row:
                row.value = value
            else:
                db.add(SystemSettings(key=key, value=value))
        db.commit()
        return True
    except Exception as exc:
        logger.warning("save_llm_config DB error: %s", exc)
        db.rollback()
        return False
    finally:
        db.close()


def update_setting(key: str, value: str) -> bool:
    """Insert or update a system setting value."""
    db = SessionLocal()
    try:
        row = db.query(SystemSettings).filter(SystemSettings.key == key).first()
        if row:
            row.value = value
        else:
            db.add(SystemSettings(key=key, value=value))
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def restore_default_settings() -> bool:
    """Delete all custom settings so values fall back to defaults."""
    db = SessionLocal()
    try:
        db.query(SystemSettings).delete()
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def get_all_overrides() -> List[Dict[str, Any]]:
    """Return all manual overrides ordered by id."""
    db = SessionLocal()
    try:
        rows = db.query(ManualOverrides).order_by(ManualOverrides.id.asc()).all()
        out: List[Dict[str, Any]] = []
        for row in rows:
            ca = row.created_at
            if ca is not None and hasattr(ca, "isoformat"):
                created_s = ca.isoformat() + 'Z'
            else:
                created_s = str(ca) if ca is not None else None
            out.append(
                {
                    "id": int(row.id),
                    "trigger_phrase": row.trigger_phrase or "",
                    "answer": row.answer or "",
                    "created_at": created_s,
                }
            )
        return out
    except Exception:
        return []
    finally:
        db.close()


def add_override(trigger_phrase: str, answer: str) -> Tuple[bool, Optional[str]]:
    """Insert a manual override row."""
    t = (trigger_phrase or "").strip()
    a = (answer or "").strip()
    if not t or not a:
        return False, "Trigger phrase and answer are required"
    db = SessionLocal()
    try:
        db.add(ManualOverrides(trigger_phrase=t, answer=a))
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def update_override(override_id: int, new_trigger: str, new_answer: str) -> Tuple[bool, Optional[str]]:
    """Update an existing manual override."""
    t = (new_trigger or "").strip()
    a = (new_answer or "").strip()
    if not t or not a:
        return False, "Trigger phrase and answer are required"
    db = SessionLocal()
    try:
        row = db.query(ManualOverrides).filter(ManualOverrides.id == int(override_id)).first()
        if not row:
            return False, "Override not found"
        row.trigger_phrase = t
        row.answer = a
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def delete_override(override_id: int) -> Tuple[bool, Optional[str]]:
    """Delete a manual override by id."""
    db = SessionLocal()
    try:
        row = db.query(ManualOverrides).filter(ManualOverrides.id == int(override_id)).first()
        if not row:
            return False, "Override not found"
        db.delete(row)
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def get_all_faqs() -> List[Dict[str, Any]]:
    """Return all FAQs ordered by latest created first."""
    db = SessionLocal()
    try:
        rows = db.query(FAQ).order_by(FAQ.display_order.asc(), FAQ.id.asc()).all()
        return [
            {
                "id": row.id,
                "question": row.question,
                "answer": row.answer,
                "display_order": int(row.display_order or 0),
                "question_count": int(row.question_count or 0),
                "created_at": row.created_at.isoformat() + 'Z' if row.created_at else None,
            }
            for row in rows
        ]
    finally:
        db.close()


def increment_faq_click(faq_id: int) -> bool:
    """Increment question_count for a specific FAQ id."""
    db = SessionLocal()
    try:
        row = db.query(FAQ).filter(FAQ.id == int(faq_id)).first()
        if not row:
            return False
        row.question_count = int(row.question_count or 0) + 1
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def add_unanswered_query(question: str, reason: str = "غير معروف") -> bool:
    """Insert a new unanswered query row with pending status."""
    q = (question or "").strip()
    if not q:
        return False
    r = (reason or "").strip() or "غير معروف"
    db = SessionLocal()
    try:
        db.add(UnansweredQueries(question=q, reason=r, status="pending"))
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def get_unanswered_queries() -> List[Dict[str, Any]]:
    """Return pending unanswered queries ordered by latest first."""
    db = SessionLocal()
    try:
        rows = (
            db.query(UnansweredQueries)
            .filter(UnansweredQueries.status == "pending")
            .order_by(UnansweredQueries.timestamp.desc(), UnansweredQueries.id.desc())
            .all()
        )
        return [
            {
                "id": int(row.id),
                "question": row.question or "",
                "reason": row.reason or "غير معروف",
                "timestamp": row.timestamp,
                "status": row.status or "pending",
            }
            for row in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def mark_query_resolved(query_id: int) -> bool:
    """Mark an unanswered query as resolved."""
    db = SessionLocal()
    try:
        row = db.query(UnansweredQueries).filter(UnansweredQueries.id == int(query_id)).first()
        if not row:
            return False
        row.status = "resolved"
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def mark_all_pending_queries_resolved(reason_filter: Optional[str] = None) -> Tuple[bool, int]:
    """Mark pending unanswered queries as resolved. If reason_filter is set, only rows with that exact reason."""
    db = SessionLocal()
    try:
        q = db.query(UnansweredQueries).filter(UnansweredQueries.status == "pending")
        if reason_filter:
            q = q.filter(UnansweredQueries.reason == reason_filter)
        rows = q.all()
        for row in rows:
            row.status = "resolved"
        db.commit()
        return True, len(rows)
    except Exception:
        db.rollback()
        return False, 0
    finally:
        db.close()


def add_faq(question: str, answer: str) -> Tuple[bool, Optional[str]]:
    """Insert a new FAQ row."""
    q = (question or "").strip()
    a = (answer or "").strip()
    if not q or not a:
        return False, "Question and answer are required"

    db = SessionLocal()
    try:
        max_order = db.query(func.max(FAQ.display_order)).scalar()
        next_order = int(max_order or 0) + 1
        row = FAQ(question=q, answer=a, display_order=next_order)
        db.add(row)
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def update_faq(
    faq_id: int,
    new_question: str,
    new_answer: str,
    new_display_order: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """Update an existing FAQ row."""
    q = (new_question or "").strip()
    a = (new_answer or "").strip()
    if not q or not a:
        return False, "Question and answer are required"

    db = SessionLocal()
    try:
        row = db.query(FAQ).filter(FAQ.id == faq_id).first()
        if not row:
            return False, "FAQ not found"
        row.question = q
        row.answer = a
        if new_display_order is not None:
            row.display_order = int(new_display_order)
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def delete_faq(faq_id: int) -> Tuple[bool, Optional[str]]:
    """Delete an FAQ row by id."""
    db = SessionLocal()
    try:
        row = db.query(FAQ).filter(FAQ.id == faq_id).first()
        if not row:
            return False, "FAQ not found"
        db.delete(row)
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def normalize_faq_order() -> Tuple[bool, Optional[str]]:
    """
    Reindex FAQ display_order to a compact sequence: 1..N.
    Preserves current relative ordering by (display_order, id).
    """
    db = SessionLocal()
    try:
        rows = db.query(FAQ).order_by(FAQ.display_order.asc(), FAQ.id.asc()).all()
        for idx, row in enumerate(rows, start=1):
            row.display_order = idx
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


# =============================================================================
# Static document freshness helpers
# =============================================================================

def get_stale_files() -> List[Dict[str, Any]]:
    """
    Return FileRecord rows that are stale or approaching their review deadline.
    A file is considered stale if:
      - status == 'stale' or 'retired'
      - valid_until is set and has passed
      - next_review_at is set and has passed
    """
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        rows = db.query(FileRecord).all()
        result = []
        for r in rows:
            reasons = []
            if r.status in ("stale", "retired"):
                reasons.append(r.status)
            if r.valid_until and r.valid_until < now:
                reasons.append("past_valid_until")
            if r.next_review_at and r.next_review_at < now:
                reasons.append("review_overdue")
            if not reasons:
                continue
            result.append({
                "id": r.id,
                "filename": r.filename,
                "original_filename": r.original_filename or r.filename,
                "status": r.status or "active",
                "valid_until": r.valid_until.isoformat() + "Z" if r.valid_until else None,
                "next_review_at": r.next_review_at.isoformat() + "Z" if r.next_review_at else None,
                "upload_date": r.upload_date.isoformat() + "Z" if r.upload_date else None,
                "reasons": reasons,
            })
        return result
    finally:
        db.close()


def update_file_freshness(
    file_record_id: int,
    source_url: Optional[str] = None,
    owner: Optional[str] = None,
    category: Optional[str] = None,
    valid_from: Optional[datetime] = None,
    valid_until: Optional[datetime] = None,
    next_review_at: Optional[datetime] = None,
    status: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Update freshness/lifecycle fields on an existing FileRecord."""
    db = SessionLocal()
    try:
        row = db.query(FileRecord).filter(FileRecord.id == file_record_id).first()
        if not row:
            return False, "FileRecord not found"
        if source_url is not None:
            row.source_url = source_url
        if owner is not None:
            row.owner = owner
        if category is not None:
            row.category = category
        if valid_from is not None:
            row.valid_from = valid_from
        if valid_until is not None:
            row.valid_until = valid_until
        if next_review_at is not None:
            row.next_review_at = next_review_at
        if status is not None:
            row.status = status
        if content_hash is not None:
            row.content_hash = content_hash
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def mark_file_reviewed(file_record_id: int, note: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Mark a file as reviewed by an admin.

    Side effects:
      - status          → 'active'
      - last_reviewed_at → now
      - next_review_at  → None  (admin just reviewed it; no pending review outstanding)
      - valid_until     → None if it was in the past (admin is confirming content is still valid)

    A DocumentVersion row is appended for audit trail.
    """
    db = SessionLocal()
    try:
        row = db.query(FileRecord).filter(FileRecord.id == file_record_id).first()
        if not row:
            return False, "FileRecord not found"
        now = datetime.utcnow()
        row.last_reviewed_at = now
        row.status = "active"
        # Clear the pending-review deadline since the admin just acted on it
        row.next_review_at = None
        # If valid_until was in the past the admin is confirming the document
        # is still current — clear the expired date so it stops showing as stale.
        # The admin can set a new valid_until via the freshness endpoint if needed.
        if row.valid_until and row.valid_until < now:
            row.valid_until = None
        # Audit entry
        latest_ver = (
            db.query(func.max(DocumentVersion.version_number))
            .filter(DocumentVersion.file_record_id == file_record_id)
            .scalar()
        ) or 0
        db.add(DocumentVersion(
            file_record_id=file_record_id,
            version_number=latest_ver,
            filename=row.filename,
            original_filename=row.original_filename,
            file_path=row.file_path,
            chunk_count=row.chunk_count or 0,
            content_hash=row.content_hash,
            action="reviewed",
            note=note,
        ))
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


# =============================================================================
# Document version (audit trail) helpers
# =============================================================================

def create_document_version(
    file_record_id: int,
    filename: str,
    original_filename: Optional[str],
    file_path: str,
    chunk_count: int,
    action: str,
    content_hash: Optional[str] = None,
    note: Optional[str] = None,
) -> bool:
    """Append a DocumentVersion row. Returns True on success."""
    db = SessionLocal()
    try:
        latest_ver = (
            db.query(func.max(DocumentVersion.version_number))
            .filter(DocumentVersion.file_record_id == file_record_id)
            .scalar()
        ) or 0
        db.add(DocumentVersion(
            file_record_id=file_record_id,
            version_number=latest_ver + 1,
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            chunk_count=chunk_count,
            content_hash=content_hash,
            action=action,
            note=note,
        ))
        db.commit()
        return True
    except Exception as e:
        logger.warning("create_document_version failed: %s", e)
        db.rollback()
        return False
    finally:
        db.close()


def get_document_versions(file_record_id: int) -> List[Dict[str, Any]]:
    """Return audit trail for a FileRecord, newest first."""
    db = SessionLocal()
    try:
        rows = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.file_record_id == file_record_id)
            .order_by(DocumentVersion.version_number.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "version_number": r.version_number,
                "filename": r.filename,
                "original_filename": r.original_filename,
                "chunk_count": r.chunk_count,
                "content_hash": r.content_hash,
                "action": r.action,
                "note": r.note,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


# =============================================================================
# Dynamic source CRUD
# =============================================================================

def _source_to_dict(row: DynamicSource) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "source_type": row.source_type,
        "endpoint_url": row.endpoint_url,
        "sync_frequency": row.sync_frequency,
        # Phase-2 scheduling fields
        "schedule_type": row.schedule_type or "manual",
        "sync_times": row.sync_times or "",
        "schedule_day": row.schedule_day or "",
        "schedule_month_day": row.schedule_month_day or "",
        "is_enabled": bool(row.is_enabled),
        "last_sync_at": row.last_sync_at.isoformat() + "Z" if row.last_sync_at else None,
        "status": row.status,
        "error_message": row.error_message,
        # auth_token is included so connectors can authenticate and
        # so the admin edit form can pre-fill the field.
        "auth_token": row.auth_token,
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        "updated_at": row.updated_at.isoformat() + "Z" if row.updated_at else None,
    }


def get_all_dynamic_sources() -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = db.query(DynamicSource).order_by(DynamicSource.id.asc()).all()
        return [_source_to_dict(r) for r in rows]
    finally:
        db.close()


def get_dynamic_source(source_id: int) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        row = db.query(DynamicSource).filter(DynamicSource.id == source_id).first()
        return _source_to_dict(row) if row else None
    finally:
        db.close()


def create_dynamic_source(
    name: str,
    source_type: str,
    endpoint_url: Optional[str] = None,
    sync_frequency: str = "manual",
    is_enabled: bool = True,
    auth_token: Optional[str] = None,
    schedule_type: str = "manual",
    sync_times: Optional[str] = None,
    schedule_day: Optional[str] = None,
    schedule_month_day: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """Insert a new DynamicSource. Returns (id, None) or (None, error)."""
    n = (name or "").strip()
    t = (source_type or "").strip()
    if not n or not t:
        return None, "name and source_type are required"
    db = SessionLocal()
    try:
        row = DynamicSource(
            name=n,
            source_type=t,
            endpoint_url=(endpoint_url or "").strip() or None,
            sync_frequency=sync_frequency or "manual",
            is_enabled=is_enabled,
            auth_token=auth_token,
            status="not_configured" if not endpoint_url else "ok",
            schedule_type=schedule_type or "manual",
            sync_times=(sync_times or "").strip() or None,
            schedule_day=(schedule_day or "").strip() or None,
            schedule_month_day=(schedule_month_day or "").strip() or None,
        )
        db.add(row)
        db.commit()
        return row.id, None
    except Exception as e:
        db.rollback()
        return None, str(e)
    finally:
        db.close()


def update_dynamic_source(
    source_id: int,
    name: Optional[str] = None,
    source_type: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    sync_frequency: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    auth_token: Optional[str] = None,
    status: Optional[str] = None,
    error_message: Optional[str] = None,
    last_sync_at: Optional[datetime] = None,
    schedule_type: Optional[str] = None,
    sync_times: Optional[str] = None,
    schedule_day: Optional[str] = None,
    schedule_month_day: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    db = SessionLocal()
    try:
        row = db.query(DynamicSource).filter(DynamicSource.id == source_id).first()
        if not row:
            return False, "DynamicSource not found"
        if name is not None:
            row.name = name.strip()
        if source_type is not None:
            row.source_type = source_type.strip()
        if endpoint_url is not None:
            row.endpoint_url = endpoint_url.strip() or None
        if sync_frequency is not None:
            row.sync_frequency = sync_frequency
        if is_enabled is not None:
            row.is_enabled = is_enabled
        if auth_token is not None:
            row.auth_token = auth_token
        if status is not None:
            row.status = status
        if error_message is not None:
            row.error_message = error_message
        if last_sync_at is not None:
            row.last_sync_at = last_sync_at
        if schedule_type is not None:
            row.schedule_type = schedule_type
        if sync_times is not None:
            row.sync_times = sync_times.strip() or None
        if schedule_day is not None:
            row.schedule_day = schedule_day.strip() or None
        if schedule_month_day is not None:
            row.schedule_month_day = schedule_month_day.strip() or None
        row.updated_at = datetime.utcnow()
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def delete_dynamic_source(source_id: int) -> Tuple[bool, Optional[str]]:
    db = SessionLocal()
    try:
        row = db.query(DynamicSource).filter(DynamicSource.id == source_id).first()
        if not row:
            return False, "DynamicSource not found"
        db.delete(row)
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


# =============================================================================
# Sync run CRUD
# =============================================================================

def _run_to_dict(row: DynamicSyncRun) -> Dict[str, Any]:
    return {
        "id": row.id,
        "source_id": row.source_id,
        "status": row.status,
        "started_at": row.started_at.isoformat() + "Z" if row.started_at else None,
        "ended_at": row.ended_at.isoformat() + "Z" if row.ended_at else None,
        "records_fetched": row.records_fetched,
        "records_changed": row.records_changed,
        "chunks_updated": row.chunks_updated,
        "error_message": row.error_message,
    }


def create_sync_run(source_id: int) -> Optional[int]:
    """Start a new sync run for a source. Returns the run id."""
    db = SessionLocal()
    try:
        run = DynamicSyncRun(source_id=source_id, status="running")
        db.add(run)
        db.commit()
        return run.id
    except Exception as e:
        logger.warning("create_sync_run failed: %s", e)
        db.rollback()
        return None
    finally:
        db.close()


def finish_sync_run(
    run_id: int,
    status: str,
    records_fetched: int = 0,
    records_changed: int = 0,
    chunks_updated: int = 0,
    error_message: Optional[str] = None,
) -> bool:
    """Mark a sync run as finished and record metrics."""
    db = SessionLocal()
    try:
        run = db.query(DynamicSyncRun).filter(DynamicSyncRun.id == run_id).first()
        if not run:
            return False
        run.status = status
        run.ended_at = datetime.utcnow()
        run.records_fetched = records_fetched
        run.records_changed = records_changed
        run.chunks_updated = chunks_updated
        run.error_message = error_message
        db.commit()
        return True
    except Exception as e:
        logger.warning("finish_sync_run failed: %s", e)
        db.rollback()
        return False
    finally:
        db.close()


def get_sync_runs(source_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent sync runs for a source, newest first."""
    db = SessionLocal()
    try:
        rows = (
            db.query(DynamicSyncRun)
            .filter(DynamicSyncRun.source_id == source_id)
            .order_by(DynamicSyncRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return [_run_to_dict(r) for r in rows]
    finally:
        db.close()
