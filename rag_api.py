# rag_api.py
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import base64
import logging
import os
import queue
import re
import requests
import sys
import threading
import time
import tempfile
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
from dotenv import load_dotenv


def _iso_json_dt(dt):
    """Return a UTC ISO string that JavaScript Date can parse consistently."""
    if dt is None:
        return None
    try:
        if getattr(dt, "tzinfo", None) is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.isoformat() + "Z"
    except Exception:
        return None


def _to_utc_naive(dt):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

sys.path.append(os.path.dirname(__file__))  # allow import from project folder

from src.rag_system import ArabicRAGChatbot, normalize_channel_answer
from src.rate_limits import (
    build_identity,
    check_and_consume,
    cost_for_text,
    cost_for_audio,
    rate_limited_message,
)
from src.utils import (
    transcribe_audio,
    LANG_NOT_SUPPORTED_MSG,
    UNCLEAR_AUDIO_MSG,
    TRANSCRIBE_FAILED_MSG,
    AUDIO_TOO_LONG_MSG,
    detect_language,
)
from sqlalchemy import func
from database import (
    init_db,
    SessionLocal,
    FileRecord,
    ChatSession,
    ChatMessage,
    Feedback,
    AdminUser,
    UPLOADS_DIR,
    delete_session as delete_chat_session,
    increment_faq_click,
    add_unanswered_query,
    verify_admin_login,
    get_all_overrides,
    add_override,
    update_override,
    delete_override,
    get_all_faqs,
    add_faq,
    update_faq,
    delete_faq,
    normalize_faq_order,
    get_unanswered_queries,
    mark_query_resolved,
    mark_all_pending_queries_resolved,
    get_setting,
    update_setting,
    restore_default_settings,
    # Dynamic source functions
    get_all_dynamic_sources,
    get_dynamic_source,
    create_dynamic_source,
    update_dynamic_source,
    delete_dynamic_source,
    get_sync_runs,
    # Static document freshness / versioning
    get_stale_files,
    update_file_freshness,
    mark_file_reviewed,
    create_document_version,
    get_document_versions,
    count_distinct_chat_users,
)

# Allowed extensions for all supported types (PDF, text, CSV, Excel, JSON)
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".csv", ".xlsx", ".xls", ".json", ".docx"}


def sanitize_filename_for_fs(name: str) -> str:
    """Make filename safe for Windows/Unix; keep original as much as possible."""
    name = os.path.basename(name).strip()
    bad = set('<>:"/\\|?*')
    out = "".join(c if c not in bad else "_" for c in name)
    return out.strip() or "upload"


def _friendly_chroma_error(exc: Exception) -> str:
    """
    Translate raw Chroma / embedding errors into user-readable Arabic messages.
    Raw technical errors are logged server-side; the admin sees a clean message.
    """
    msg = str(exc).lower()
    if 'non-empty' in msg or 'empty' in msg or '[]' in msg:
        return 'لم يتم استخراج أي نص من الملف. قد يكون الملف فارغاً، يحتوي على صور فقط، أو تالفاً.'
    if 'connection' in msg or 'refused' in msg or 'timeout' in msg:
        return 'تعذر الاتصال بخادم التضمين (Ollama). تأكد من أنه يعمل وحاول مجدداً.'
    if 'unicode' in msg or 'encoding' in msg or 'decode' in msg:
        return 'تعذر قراءة ترميز الملف. حاول حفظه بترميز UTF-8 ثم أعد رفعه.'
    if 'permission' in msg:
        return 'خطأ في صلاحيات الوصول إلى الملف على الخادم.'
    # Generic fallback — hide raw internals from the UI
    app.logger.error("Chroma/indexing error: %s", exc)
    return 'حدث خطأ أثناء فهرسة الملف. يرجى المحاولة مرة أخرى أو التواصل مع المسؤول التقني.'


def make_unique_stored_name(original_filename: str) -> str:
    """
    Use the original filename in uploads/ (sanitized). If it already exists,
    add (1), (2), ... so we don't overwrite. Same name is used in DB and Chroma.
    """
    base = sanitize_filename_for_fs(original_filename)
    stem, ext = os.path.splitext(base)
    if not ext or ext.lower() not in ALLOWED_EXTENSIONS:
        ext = ".bin"
    stored_name = stem + ext
    path = os.path.join(UPLOADS_DIR, stored_name)
    n = 0
    while os.path.isfile(path) or _filename_exists_in_db(stored_name):
        n += 1
        stored_name = f"{stem} ({n}){ext}"
        path = os.path.join(UPLOADS_DIR, stored_name)
    return stored_name


def _filename_exists_in_db(filename: str) -> bool:
    db = SessionLocal()
    try:
        return db.query(FileRecord).filter(FileRecord.filename == filename).first() is not None
    finally:
        db.close()

import jwt
from functools import wraps

app = Flask(__name__)
CORS(app)  # allow requests from Streamlit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# database.py loads .env on import; reload here so env is available if import order changes
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env_str(key: str, default: str = "") -> str:
    return (os.getenv(key, default) or "").strip()


# Webhook / platform secrets — set in .env (see .env.example)
TELEGRAM_BOT_TOKEN = _env_str("TELEGRAM_BOT_TOKEN") or None
WHATSAPP_ACCESS_TOKEN = _env_str("WHATSAPP_ACCESS_TOKEN") or None
WHATSAPP_PHONE_NUMBER_ID = _env_str("WHATSAPP_PHONE_NUMBER_ID") or None
WHATSAPP_VERIFY_TOKEN = _env_str("WHATSAPP_VERIFY_TOKEN") or None
MESSENGER_PAGE_ACCESS_TOKEN = _env_str("MESSENGER_PAGE_ACCESS_TOKEN") or None
MESSENGER_VERIFY_TOKEN = _env_str("MESSENGER_VERIFY_TOKEN") or None
WHATSAPP_GRAPH_API_VERSION = _env_str("WHATSAPP_GRAPH_API_VERSION", "v17.0") or "v17.0"
MESSENGER_GRAPH_API_VERSION = _env_str("MESSENGER_GRAPH_API_VERSION", "v19.0") or "v19.0"
TELEGRAM_PARSE_MODE = _env_str("TELEGRAM_PARSE_MODE") or None
RAG_API_HOST = _env_str("RAG_API_HOST", "0.0.0.0") or "0.0.0.0"
try:
    RAG_API_PORT = int(_env_str("RAG_API_PORT", "5000") or "5000")
except ValueError:
    RAG_API_PORT = 5000

JWT_SECRET_KEY = _env_str("JWT_SECRET_KEY", "changeme-hebron-admin-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 12

ADMIN_SETTING_KEYS = [
    "ar_system_prompt",
    "en_system_prompt",
    "ar_dont_know",
    "en_dont_know",
    "ar_low_conf",
    "en_low_conf",
    "lang_not_supported",
    "ar_out_of_scope",
    "en_out_of_scope",
]


def _make_jwt(username: str, role: str) -> str:
    from datetime import timedelta
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def require_admin(f):
    """Decorator: validates Bearer JWT on /api/admin/* routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = auth[len("Bearer "):]
        try:
            jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


def _resolve_persist_dir() -> str:
    """
    Chroma persistence path. If `PERSIST_DIR` is missing or empty in `.env`, use
    `<project>/chroma_db`. (Note: `os.getenv("PERSIST_DIR", default)` returns
    "" when the key exists but is empty, which would break loading — so we
    must treat empty like unset.)
    Relative values are resolved under the project directory.
    """
    raw = (os.getenv("PERSIST_DIR") or "").strip()
    if not raw:
        return os.path.join(BASE_DIR, "chroma_db")
    return raw if os.path.isabs(raw) else os.path.normpath(os.path.join(BASE_DIR, raw))


# Create DB tables and uploads directory on startup
init_db()

# Initialize the chatbot (same settings as before)
chatbot = ArabicRAGChatbot(
    llm_model=os.getenv("LLM_MODEL", "deepseek-v3.1:671b-cloud"),
    embed_model=os.getenv("EMBED_MODEL", "bge-m3"),
    persist_dir=_resolve_persist_dir(),
    ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    retrieval_strategy=os.getenv("RETRIEVAL_STRATEGY", "mmr"),
)

# Dynamic ingestion service (shares the chatbot instance for Chroma access)
from src.dynamic_ingestion import DynamicIngestionService  # noqa: E402
ingestion_service = DynamicIngestionService(chatbot)

# =============================================================================
# APScheduler — auto-sync scheduler
# =============================================================================

_scheduler = BackgroundScheduler(daemon=True, timezone="UTC")


def _remove_source_jobs(source_id: int) -> None:
    """Remove all scheduled jobs that belong to a given source."""
    prefix = f"sync_{source_id}_"
    for job in _scheduler.get_jobs():
        if job.id.startswith(prefix):
            try:
                _scheduler.remove_job(job.id)
            except Exception:
                pass


def _schedule_source(source: dict) -> None:
    """
    Register APScheduler cron jobs for *source* based on its scheduling fields.
    Existing jobs for this source are removed first so the function is idempotent
    (safe to call on both create and update).
    """
    source_id = source["id"]
    _remove_source_jobs(source_id)

    stype = (source.get("schedule_type") or "manual").lower()
    raw_times = (source.get("sync_times") or "").strip()

    if stype == "manual" or not raw_times or not source.get("is_enabled", True):
        return

    time_entries = [t.strip() for t in raw_times.split(",") if t.strip()]
    s_day = (source.get("schedule_day") or "").strip()       # e.g. "0,2,4"
    s_mday = (source.get("schedule_month_day") or "").strip()  # e.g. "1,15"

    for idx, time_str in enumerate(time_entries):
        try:
            h_str, m_str = time_str.split(":")
            h, m = int(h_str), int(m_str)
        except Exception:
            logger.warning("Scheduler: could not parse time '%s' for source %s", time_str, source_id)
            continue

        cron_kwargs: dict = {"hour": h, "minute": m}
        if stype == "weekly" and s_day:
            cron_kwargs["day_of_week"] = s_day
        elif stype == "monthly" and s_mday:
            cron_kwargs["day"] = s_mday

        job_id = f"sync_{source_id}_{idx}"
        try:
            _scheduler.add_job(
                ingestion_service.sync_source,
                CronTrigger(**cron_kwargs),
                id=job_id,
                args=[source_id],
                replace_existing=True,
                misfire_grace_time=3600,
            )
            logger.info(
                "Scheduler: registered job %s for source %s (%s) cron=%s",
                job_id, source_id, stype, cron_kwargs,
            )
        except Exception as exc:
            logger.warning("Scheduler: could not add job %s: %s", job_id, exc)


def _bootstrap_scheduler() -> None:
    """Load all enabled sources from DB and schedule their jobs, then start the scheduler."""
    sources = get_all_dynamic_sources()
    for src in sources:
        if src.get("is_enabled"):
            _schedule_source(src)
    _scheduler.start()
    logger.info("APScheduler started — %d source(s) loaded", len([s for s in sources if s.get("is_enabled")]))


# Start the scheduler immediately (works for both direct run and gunicorn/waitress)
_bootstrap_scheduler()


def _first_n_words(text: str, n: int = 5) -> str:
    """First n words of text for use as session title."""
    parts = (text or "").strip().split()
    return " ".join(parts[:n]) if parts else "New Chat"


def check_manual_overrides(user_question: str) -> str | None:
    """
    If any comma-separated trigger phrase appears as a substring of the user's text,
    and that match is not drowned out by unrelated text (hybrid question), return the
    hardcoded answer.

    Uses the *longest* matching phrase per row (not the first in the list) so a short
    prefix does not steal the match from a longer phrase that fits the user better.
    """
    overrides = get_all_overrides()
    clean_user = re.sub(r'[؟?.,!،]', '', user_question).strip().lower()

    if not clean_user:
        return None

    matched_answers: list[str] = []
    matched_length = 0
    user_len = len(clean_user)

    for override in overrides:
        raw = override.get("trigger_phrase") or ""
        trigger_variations = re.split(r"[,،/|]", raw)

        best_len = 0
        for variation in trigger_variations:
            clean_trigger = re.sub(r'[؟?.,!،]', '', variation).strip().lower()
            if clean_trigger and clean_trigger in clean_user:
                best_len = max(best_len, len(clean_trigger))

        if best_len > 0:
            matched_answers.append(override["answer"])
            matched_length += best_len

    if not matched_answers:
        return None

    # Hybrid guard: require most of the message to be covered by matched trigger text.
    # 70% was too strict: a user can match a *shorter* listed phrase inside a longer
    # sentence (same topic), so matched_length/user_len drops below 70% even though
    # the question is not a "hybrid" of unrelated topics.
    if matched_length >= user_len * 0.70:
        return "\n\n".join(matched_answers)

    return None


def ask_with_history(session_id: str, platform: str, user_text: str,
                     is_audio: bool = False) -> str:
    """
    Load last 10 DB messages, run RAG, persist ChatSession + ChatMessage rows
    (user_id=platform), return bot text.

    is_audio  True when the original message was a voice/audio clip — uses a
              higher rate-limit cost than plain text.
    """
    override_answer = check_manual_overrides(user_text)
    if override_answer is not None:
        bot_response = override_answer
        gen_time = None
        retrieval_context = ""
    else:
        # --- Rate limit check (LLM path only; overrides are free) ---
        rl_cost = cost_for_audio() if is_audio else cost_for_text(user_text)
        rl_identity = build_identity(platform, session_id)
        rl_decision = check_and_consume(rl_identity, rl_cost)
        if not rl_decision.allowed:
            logger.info(
                "Rate limited platform=%s identity=%s retry_after=%ss",
                platform, rl_identity, rl_decision.retry_after_seconds,
            )
            return normalize_channel_answer(
                rate_limited_message(rl_decision.retry_after_seconds)
            )
        # ------------------------------------------------------------------

        chat_history = []
        db = SessionLocal()
        try:
            past_msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.timestamp.asc())
                .all()
            )
            for msg in past_msgs[-10:]:
                chat_history.append({"role": msg.role, "content": msg.content})
        except Exception:
            pass
        finally:
            db.close()

        retrieval_context = ""
        start_time = time.time()
        try:
            bot_response, retrieval_context = chatbot.ask_with_context(
                question=user_text,
                session_id=session_id,
                history=chat_history,
            )
            gen_time = round(time.time() - start_time, 2)
        except Exception as e:
            if platform == "telegram":
                bot_response = "عذراً، حدث خطأ داخلي أثناء معالجة طلبك."
            else:
                bot_response = "عذراً، حدث خطأ أثناء معالجة رسالتك."
            print(f"RAG Error: {e}")
            gen_time = None

        _log_unanswered_with_reason(user_text, bot_response, retrieval_context)

    db = SessionLocal()
    try:
        sess = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        is_new = not sess
        if not sess:
            sess = ChatSession(
                session_id=session_id,
                user_id=platform,
                title="New Chat",
            )
            db.add(sess)
            db.commit()
        user_msg = ChatMessage(session_id=session_id, role="user", content=user_text)
        db.add(user_msg)
        bot_msg = ChatMessage(
            session_id=session_id,
            role="bot",
            content=bot_response,
            generation_time=gen_time,
        )
        db.add(bot_msg)
        db.commit()
        if is_new:
            sess.title = _first_n_words(user_text, 5)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    return normalize_channel_answer(bot_response)


def _answer_suggests_faq(answer: str) -> bool:
    """
    True when the bot reply indicates uncertainty, empty KB, or errors —
    frontend can surface predefined FAQs as follow-ups.
    """
    if not answer or not str(answer).strip():
        return True
    a = str(answer).strip()
    markers = [
        "عذراً، قاعدة المعرفة فارغة",
        "عذراً، لم أتمكن من العثور على معلومات دقيقة",
        "لم أتمكن من العثور على معلومات دقيقة",
        "The knowledge base has no documents",
        "Error:",
        "عذراً، حدث خطأ",
        get_setting("ar_dont_know").strip(),
        get_setting("en_dont_know").strip(),
        get_setting("ar_low_conf").strip(),
        get_setting("en_low_conf").strip(),
    ]
    markers = [m for m in markers if m]
    return any(m in a for m in markers)


def _should_log_unanswered(answer: str) -> bool:
    """
    Detect fallback/unanswered replies that indicate missing knowledge.
    """
    a = (answer or "").strip()
    if not a:
        return True
    if _answer_suggests_faq(a):
        return True
    lower = a.lower()
    return any(marker in lower for marker in ("i don't know", "i do not know"))


REASON_UNSUPPORTED_LANG = "السؤال ليس بالعربية أو الإنجليزية"
REASON_NO_CONTEXT = "لا يوجد سياق مطابق في قاعدة البيانات"
REASON_OUT_OF_SCOPE = "السؤال خارج نطاق جامعة الخليل أو لا يتعلق بخدماتها"
REASON_MODEL = "النموذج لم يتمكن من استخراج الإجابة من السياق"


def _is_supported_chat_language(text: str) -> bool:
    """Same rule as ArabicRAGChatbot.ask_with_context: only Arabic and English are supported."""
    raw = (text or "").strip()
    if not raw:
        return True
    try:
        return detect_language(raw) in ("ar", "en")
    except Exception:
        return True


def _question_likely_university_related(question: str) -> bool:
    """
    Heuristic aligned with the Hebron University assistant role (get_prompt):
    if none of these themes appear, the question is treated as outside university scope
    when the bot still could not answer with context present.
    """
    q = (question or "").strip()
    if len(q) < 5:
        return True
    ql = q.lower()
    if "non-supported language" in ql or "original text:" in ql:
        return True
    patterns = (
        r"جامعة",
        r"الخليل",
        r"خَليل",
        r"hebron",
        r"university",
        r"كلية",
        r"قسم",
        r"عمادة",
        r"تسجيل",
        r"قبول",
        r"برنامج",
        r"طالب",
        r"طلاب",
        r"student",
        r"faculty",
        r"department",
        r"campus",
        r"شهادة",
        r"امتحان",
        r"exam",
        r"course",
        r"registration",
        r"admission",
        r"بحث",
        r"رسوم",
        r"تسديد",
        r"fee",
        r"tuition",
        r"scholarship",
        r"منحة",
        r"ماجستير",
        r"دكتوراه",
        r"bachelor",
        r"مكتبة",
        r"library",
        r"دبلوم",
        r"diploma",
        r"نظام",
        r"دراسة",
        r"study",
        r"تخرج",
        r"graduate",
        r"وثيقة",
        r"شهادة",
    )
    for pat in patterns:
        if re.search(pat, q, re.IGNORECASE):
            return True
    return False


def _log_unanswered_with_reason(user_question: str, answer: str, retrieval_context: str) -> None:
    """
    Log to unanswered_queries with a specific reason:
    unsupported language, no retrieval, out of university scope, or model could not use context.
    """
    q = (user_question or "").strip()
    if not q:
        return

    # 1) Not Arabic / English — same path as ask_with_context rewriting to a meta-instruction (get_prompt still English).
    if not _is_supported_chat_language(q):
        add_unanswered_query(q, REASON_UNSUPPORTED_LANG)
        return

    if not _should_log_unanswered(answer):
        return

    ctx = (retrieval_context or "").strip()
    if not ctx or len(ctx) < 10:
        add_unanswered_query(q, REASON_NO_CONTEXT)
        return

    # 2) Context present (per prompt: grounded in Hebron University materials only).
    if not _question_likely_university_related(q):
        add_unanswered_query(q, REASON_OUT_OF_SCOPE)
        return

    add_unanswered_query(q, REASON_MODEL)


@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json or {}
        question = (data.get('question') or '').strip()
        session_id = (data.get('session_id') or '').strip() or None
        user_id = (data.get('user_id') or '').strip() or None
        if not question:
            return jsonify({'error': 'No question provided'}), 400

        override_answer = check_manual_overrides(question)
        chat_history = []
        db = None
        if session_id and override_answer is None:
            db = SessionLocal()
            try:
                past_msgs = (
                    db.query(ChatMessage)
                    .filter(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.timestamp.asc())
                    .all()
                )
                for msg in past_msgs[-10:]:
                    chat_history.append({"role": msg.role, "content": msg.content})
            except Exception:
                pass
            # db kept open for saving user/bot messages below

        if override_answer is not None:
            answer = override_answer
            retrieval_context = ""
            gen_time = None
        else:
            # --- Rate limit check (LLM path only; overrides/FAQs are free) ---
            rl_identity = build_identity(
                "web",
                user_id or session_id or request.remote_addr or "anon",
            )
            rl_cost = cost_for_text(question)
            rl_decision = check_and_consume(rl_identity, rl_cost)
            if not rl_decision.allowed:
                logger.info(
                    "Rate limited web user identity=%s retry_after=%ss",
                    rl_identity, rl_decision.retry_after_seconds,
                )
                if db is not None:
                    db.close()
                return jsonify({
                    'answer': rate_limited_message(rl_decision.retry_after_seconds),
                    'message_id': None,
                    'session_created': False,
                    'suggest_faq': False,
                    **rl_decision.as_json,
                }), 429
            # ------------------------------------------------------------------

            start_time = time.time()
            answer, retrieval_context = chatbot.ask_with_context(
                question, session_id=session_id, history=chat_history
            )
            end_time = time.time()
            gen_time = round(end_time - start_time, 2)
            _log_unanswered_with_reason(question, answer, retrieval_context)

        answer = normalize_channel_answer(answer)

        message_id = None
        session_created = False

        if session_id:
            if db is None:
                db = SessionLocal()
            try:
                sess = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
                is_new = not sess
                if is_new:
                    session_created = True
                if not sess:
                    sess = ChatSession(
                        session_id=session_id,
                        user_id=user_id or "",
                        title="New Chat",
                    )
                    db.add(sess)
                    db.commit()

                # Save user message then bot message
                user_msg = ChatMessage(session_id=session_id, role='user', content=question)
                db.add(user_msg)
                bot_msg = ChatMessage(session_id=session_id, role='bot', content=answer, generation_time=gen_time)
                db.add(bot_msg)
                db.commit()
                message_id = bot_msg.id

                # First message in this session: set title to first 5 words of question
                if is_new:
                    sess.title = _first_n_words(question, 5)
                    db.commit()
            except Exception as e:
                db.rollback()
                pass
            finally:
                db.close()

        return jsonify({
            'answer': answer,
            'message_id': message_id,
            'session_created': session_created,
            'suggest_faq': _answer_suggests_faq(answer),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/chat/faq', methods=['POST'])
def chat_faq():
    """
    Persist a predefined FAQ Q/A pair without invoking RAG/LLM.
    Expects JSON: { faq_id, question, answer, session_id, user_id }.
    """
    try:
        data = request.json or {}
        question = (data.get('question') or '').strip()
        answer = (data.get('answer') or '').strip()
        faq_id = data.get('faq_id')
        session_id = (data.get('session_id') or '').strip() or None
        user_id = (data.get('user_id') or '').strip() or None

        if not question or not answer:
            return jsonify({'error': 'question and answer are required'}), 400
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400

        if faq_id is not None:
            try:
                increment_faq_click(int(faq_id))
            except Exception:
                pass

        db = SessionLocal()
        try:
            sess = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            is_new = not sess
            if not sess:
                sess = ChatSession(
                    session_id=session_id,
                    user_id=user_id or "",
                    title="New Chat",
                )
                db.add(sess)
                db.commit()

            user_msg = ChatMessage(session_id=session_id, role='user', content=question)
            db.add(user_msg)
            # No RAG/LLM timing — leave null so KPI avg excludes FAQ answers
            bot_msg = ChatMessage(session_id=session_id, role='bot', content=answer, generation_time=None)
            db.add(bot_msg)
            db.commit()

            if is_new:
                sess.title = _first_n_words(question, 5)
                db.commit()

            return jsonify({
                'ok': True,
                'message_id': bot_msg.id,
                'session_created': is_new,
            })
        except Exception as e:
            db.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            db.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/chat/audio', methods=['POST'])
def chat_audio():
    temp_file_path = None
    try:
        audio_file = request.files.get("audio")
        if not audio_file:
            return jsonify({'error': 'No audio file provided'}), 400

        transcribe_only = (request.form.get("transcribe_only") or "").strip().lower() in ("1", "true", "yes")
        session_id = (request.form.get("session_id") or "").strip() or None
        user_id = (request.form.get("user_id") or "").strip() or "streamlit-widget"

        original_name = (audio_file.filename or "").lower()
        suffix = os.path.splitext(original_name)[1] or ".webm"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="temp_st_") as tmp:
            temp_file_path = tmp.name
            audio_file.save(temp_file_path)

        question = transcribe_audio(temp_file_path)
        if not question or question in {LANG_NOT_SUPPORTED_MSG, UNCLEAR_AUDIO_MSG, TRANSCRIBE_FAILED_MSG, AUDIO_TOO_LONG_MSG}:
            return jsonify({'error': question or 'Audio transcription returned empty text'}), 422

        if transcribe_only:
            return jsonify({
                'transcription': question,
            })

        # Keep behavior aligned with /chat by reusing same ask/save flow.
        if session_id:
            # is_audio=True so cost_for_audio() is applied inside ask_with_history
            answer = ask_with_history(session_id, user_id, question, is_audio=True)
        else:
            override_answer = check_manual_overrides(question)
            if override_answer is not None:
                answer = override_answer
            else:
                # --- Rate limit check for sessionless audio path ---
                rl_identity = build_identity("web", user_id or request.remote_addr or "anon")
                rl_decision = check_and_consume(rl_identity, cost_for_audio())
                if not rl_decision.allowed:
                    logger.info(
                        "Rate limited audio (no session) identity=%s retry_after=%ss",
                        rl_identity, rl_decision.retry_after_seconds,
                    )
                    return jsonify({
                        'answer': rate_limited_message(rl_decision.retry_after_seconds),
                        'transcription': question,
                        'message_id': None,
                        'session_created': False,
                        **rl_decision.as_json,
                    }), 429
                # ---------------------------------------------------
                answer = chatbot.ask(question, session_id=None, history=[])

        answer = normalize_channel_answer(answer)

        return jsonify({
            'answer': answer,
            'transcription': question,
            'message_id': None,
            'session_created': False,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass


# --- Webhook queues: Telegram / WhatsApp / Messenger ---

telegram_queue = queue.Queue()
seen_telegram_update_ids = set()
whatsapp_queue = queue.Queue()
seen_whatsapp_message_ids = set()
message_queue = queue.Queue()
seen_message_ids = set()


def telegram_background_worker():
    while True:
        chat_id, payload = telegram_queue.get()
        try:
            user_text = ""
            is_audio_msg = payload.get("type") == "voice"
            if is_audio_msg:
                file_id = payload.get("file_id")
                if not TELEGRAM_BOT_TOKEN or not file_id:
                    continue
                temp_file_path = None
                try:
                    get_file_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
                    get_file_resp = requests.get(get_file_url, params={"file_id": file_id}, timeout=30)
                    get_file_resp.raise_for_status()
                    file_result = (get_file_resp.json() or {}).get("result") or {}
                    file_path = file_result.get("file_path")
                    if not file_path:
                        raise ValueError("Telegram file_path not found")

                    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg", prefix="temp_tg_") as tmp:
                        temp_file_path = tmp.name
                    with requests.get(download_url, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(temp_file_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    user_text = transcribe_audio(temp_file_path)
                except Exception as e:
                    print(f"Telegram voice processing error: {e}")
                    user_text = TRANSCRIBE_FAILED_MSG
                finally:
                    if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.remove(temp_file_path)
                        except OSError:
                            pass
            else:
                user_text = (payload.get("text") or "").strip()

            if not user_text:
                continue
            if user_text in {LANG_NOT_SUPPORTED_MSG, UNCLEAR_AUDIO_MSG, TRANSCRIBE_FAILED_MSG, AUDIO_TOO_LONG_MSG}:
                bot_response = user_text
            else:
                bot_response = ask_with_history(str(chat_id), "telegram", user_text,
                                                is_audio=is_audio_msg)
            if TELEGRAM_BOT_TOKEN:
                telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {"chat_id": chat_id, "text": bot_response}
                if TELEGRAM_PARSE_MODE:
                    payload["parse_mode"] = TELEGRAM_PARSE_MODE
                response = requests.post(telegram_api_url, json=payload)
                if response.status_code not in [200, 201]:
                    print(f"❌ Telegram API Error [{response.status_code}]: {response.text}")
                else:
                    print("✅ Telegram message sent successfully!")
            else:
                print("Telegram: TELEGRAM_BOT_TOKEN not set; skipping send to Telegram.")
        except Exception as e:
            print(f"Worker Error: {e}")


def whatsapp_background_worker():
    while True:
        sender_phone, payload = whatsapp_queue.get()
        try:
            user_text = ""
            is_audio_msg = payload.get("type") == "audio"
            if is_audio_msg:
                media_id = payload.get("id")
                if not WHATSAPP_ACCESS_TOKEN or not media_id:
                    continue
                temp_file_path = None
                try:
                    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
                    media_meta_url = f"https://graph.facebook.com/{WHATSAPP_GRAPH_API_VERSION}/{media_id}"
                    media_meta_resp = requests.get(media_meta_url, headers=headers, timeout=30)
                    media_meta_resp.raise_for_status()
                    media_url = (media_meta_resp.json() or {}).get("url")
                    if not media_url:
                        raise ValueError("WhatsApp media URL not found")

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg", prefix="temp_wa_") as tmp:
                        temp_file_path = tmp.name
                    with requests.get(media_url, headers=headers, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(temp_file_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    user_text = transcribe_audio(temp_file_path)
                except Exception as e:
                    print(f"WhatsApp audio processing error: {e}")
                    user_text = TRANSCRIBE_FAILED_MSG
                finally:
                    if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.remove(temp_file_path)
                        except OSError:
                            pass
            else:
                user_text = (payload.get("text") or "").strip()

            if not user_text:
                continue
            if user_text in {LANG_NOT_SUPPORTED_MSG, UNCLEAR_AUDIO_MSG, TRANSCRIBE_FAILED_MSG, AUDIO_TOO_LONG_MSG}:
                bot_response = user_text
            else:
                bot_response = ask_with_history(str(sender_phone), "whatsapp", user_text,
                                                is_audio=is_audio_msg)
            if WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID:
                whatsapp_api_url = (
                    f"https://graph.facebook.com/{WHATSAPP_GRAPH_API_VERSION}/"
                    f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
                )
                headers = {
                    "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "messaging_product": "whatsapp",
                    "to": sender_phone,
                    "type": "text",
                    "text": {"body": bot_response},
                }
                response = requests.post(whatsapp_api_url, headers=headers, json=payload)
                if response.status_code not in [200, 201]:
                    print(f"❌ WhatsApp API Error [{response.status_code}]: {response.text}")
                else:
                    print("✅ WhatsApp message sent successfully!")
            else:
                print(
                    "WhatsApp: WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID not set; "
                    "skipping send to WhatsApp Cloud API."
                )
        except Exception as e:
            print(f"Worker Error: {e}")


def background_worker():
    while True:
        sender_id, payload = message_queue.get()
        try:
            user_text = ""
            is_audio_msg = payload.get("type") == "audio"
            if is_audio_msg:
                audio_url = payload.get("url")
                if not audio_url:
                    continue
                temp_file_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", prefix="temp_ms_") as tmp:
                        temp_file_path = tmp.name
                    with requests.get(audio_url, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(temp_file_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    user_text = transcribe_audio(temp_file_path)
                except Exception as e:
                    print(f"Messenger audio processing error: {e}")
                    user_text = TRANSCRIBE_FAILED_MSG
                finally:
                    if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.remove(temp_file_path)
                        except OSError:
                            pass
            else:
                user_text = (payload.get("text") or "").strip()

            if not user_text:
                continue
            if user_text in {LANG_NOT_SUPPORTED_MSG, UNCLEAR_AUDIO_MSG, TRANSCRIBE_FAILED_MSG, AUDIO_TOO_LONG_MSG}:
                bot_response = user_text
            else:
                bot_response = ask_with_history(str(sender_id), "messenger", user_text,
                                                is_audio=is_audio_msg)
            if MESSENGER_PAGE_ACCESS_TOKEN:
                messenger_api_url = (
                    f"https://graph.facebook.com/{MESSENGER_GRAPH_API_VERSION}/me/messages"
                )
                headers = {"Content-Type": "application/json"}
                payload = {
                    "recipient": {"id": str(sender_id)},
                    "message": {"text": bot_response},
                }
                response = requests.post(
                    messenger_api_url,
                    params={"access_token": MESSENGER_PAGE_ACCESS_TOKEN},
                    headers=headers,
                    json=payload,
                )
                if response.status_code not in [200, 201]:
                    print(f"❌ Messenger API Error [{response.status_code}]: {response.text}")
                else:
                    print("✅ Messenger message sent successfully!")
            else:
                print("Messenger: MESSENGER_PAGE_ACCESS_TOKEN not set; skipping send to Messenger API.")
        except Exception as e:
            print(f"Worker Error: {e}")


threading.Thread(target=telegram_background_worker, daemon=True).start()
threading.Thread(target=whatsapp_background_worker, daemon=True).start()
threading.Thread(target=background_worker, daemon=True).start()


@app.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    data = request.json or {}
    message = data.get("message") or {}
    if message:
        update_id = data.get("update_id")
        if update_id is not None:
            if update_id in seen_telegram_update_ids:
                return jsonify({"status": "ok"}), 200
            seen_telegram_update_ids.add(update_id)
        chat_id = (message.get("chat") or {}).get("id")
        if not chat_id:
            return jsonify({"status": "ok"}), 200

        if message.get("text"):
            telegram_queue.put((chat_id, {"type": "text", "text": message.get("text")}))
        elif message.get("voice") or message.get("audio"):
            voice_obj = message.get("voice") or message.get("audio") or {}
            file_id = voice_obj.get("file_id")
            if file_id:
                telegram_queue.put((chat_id, {"type": "voice", "file_id": file_id}))
    return jsonify({"status": "ok"}), 200


@app.route('/webhook/whatsapp', methods=['GET', 'POST'])
def whatsapp_webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if (
            mode == 'subscribe'
            and WHATSAPP_VERIFY_TOKEN
            and token == WHATSAPP_VERIFY_TOKEN
            and challenge is not None
        ):
            print("WhatsApp Webhook Verified!")
            return str(challenge), 200
        return "Verification failed", 403

    if request.method == 'POST':
        data = request.json or {}
        try:
            for entry in data.get('entry') or []:
                for change in entry.get('changes') or []:
                    value = change.get('value') or {}
                    # Status-only updates (read, delivered, sent) have no user message to answer
                    if 'messages' not in value:
                        continue
                    for message in value.get('messages') or []:
                        sender_phone = message.get('from')
                        if not sender_phone:
                            continue

                        message_id = message.get('id')
                        if not message_id:
                            continue
                        if message_id in seen_whatsapp_message_ids:
                            continue
                        seen_whatsapp_message_ids.add(message_id)

                        if message.get('type') == 'text':
                            text_obj = message.get('text') or {}
                            user_text = text_obj.get('body')
                            if user_text:
                                whatsapp_queue.put((sender_phone, {"type": "text", "text": user_text}))
                        elif message.get('type') == 'audio':
                            audio_obj = message.get('audio') or {}
                            media_id = audio_obj.get('id')
                            if media_id:
                                whatsapp_queue.put((sender_phone, {"type": "audio", "id": media_id}))
        except Exception as e:
            print(f"Error parsing WhatsApp webhook: {e}")

        return jsonify({"status": "ok"}), 200


# --- Facebook Messenger Webhook Integration ---


@app.route('/webhook/messenger', methods=['GET', 'POST'])
def messenger_webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if (
            mode == 'subscribe'
            and MESSENGER_VERIFY_TOKEN
            and token == MESSENGER_VERIFY_TOKEN
            and challenge is not None
        ):
            print("Messenger Webhook Verified!")
            return str(challenge), 200
        return "Verification failed", 403

    if request.method == 'POST':
        data = request.json or {}
        try:
            if data.get('object') == 'page':
                for entry in data.get('entry') or []:
                    for messaging_event in entry.get('messaging') or []:
                        msg = messaging_event.get('message') or {}
                        # Deliveries, reads, and other non-message events
                        if not msg:
                            continue
                        # Ignore echoes of our own sends (avoids loops)
                        if msg.get('is_echo'):
                            continue
                        user_text = msg.get('text')
                        sender_id = (messaging_event.get('sender') or {}).get('id')
                        if not sender_id:
                            continue

                        message_id = messaging_event["message"].get("mid")
                        if not message_id:
                            continue
                        if message_id in seen_message_ids:
                            continue
                        seen_message_ids.add(message_id)
                        attachments = msg.get("attachments") or []
                        if attachments and attachments[0].get("type") == "audio":
                            payload = (attachments[0].get("payload") or {})
                            audio_url = payload.get("url")
                            if audio_url:
                                message_queue.put((sender_id, {"type": "audio", "url": audio_url}))
                                continue
                        if user_text:
                            message_queue.put((sender_id, {"type": "text", "text": user_text}))
        except Exception as e:
            print(f"Error parsing Messenger webhook: {e}")

        return jsonify({"status": "ok"}), 200


@app.route('/users/<path:user_id>/sessions', methods=['GET'])
def user_sessions(user_id):
    """List sessions for this user by most recent message activity."""
    user_key = (user_id or "").strip()
    db = SessionLocal()
    try:
        sessions = (
            db.query(ChatSession)
            .filter(ChatSession.user_id == user_key)
            .all()
        )
        if not sessions:
            return jsonify([])

        session_ids = [s.session_id for s in sessions]
        max_rows = (
            db.query(ChatMessage.session_id, func.max(ChatMessage.timestamp).label("last_ts"))
            .filter(ChatMessage.session_id.in_(session_ids))
            .group_by(ChatMessage.session_id)
            .all()
        )
        last_message_by_session = {sid: ts for sid, ts in max_rows}

        def activity_ts(sess):
            dt = last_message_by_session.get(sess.session_id) or sess.start_time
            if dt is None:
                return 0.0
            try:
                naive = _to_utc_naive(dt)
                if naive is None:
                    return 0.0
                return naive.replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                return 0.0

        sessions_sorted = sorted(
            sessions,
            key=lambda s: (activity_ts(s), s.session_id or ""),
            reverse=True,
        )

        return jsonify([
            {
                "session_id": s.session_id,
                "title": s.title or "New Chat",
                "start_time": _iso_json_dt(s.start_time),
                "last_message_time": _iso_json_dt(last_message_by_session.get(s.session_id)),
            }
            for s in sessions_sorted
        ])
    finally:
        db.close()


@app.route('/sessions/<path:session_id>/messages', methods=['GET'])
def session_messages(session_id):
    """List messages in this session, chronological order."""
    db = SessionLocal()
    try:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.timestamp.asc())
            .all()
        )
        return jsonify([
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "timestamp": _iso_json_dt(m.timestamp),
            }
            for m in messages
        ])
    finally:
        db.close()


@app.route('/sessions/<path:session_id>', methods=['DELETE'])
def delete_session_route(session_id):
    """Delete session and all its messages and feedback."""
    ok, err = delete_chat_session(session_id)
    if not ok:
        if err == "Session not found":
            return jsonify({'error': err}), 404
        return jsonify({'error': err}), 500
    return jsonify({'message': 'Session deleted'})


@app.route('/feedback', methods=['POST'])
def feedback():
    """Accept JSON: { message_id, rating } where rating is 'like' or 'dislike'."""
    try:
        data = request.json or {}
        message_id = data.get('message_id')
        rating = (data.get('rating') or '').strip().lower()
        if message_id is None:
            return jsonify({'error': 'message_id required'}), 400
        if rating not in ('like', 'dislike'):
            return jsonify({'error': 'rating must be like or dislike'}), 400
        db = SessionLocal()
        try:
            rec = Feedback(message_id=int(message_id), rating=rating)
            db.add(rec)
            db.commit()
            return jsonify({'ok': True})
        except Exception as e:
            db.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            db.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/analytics', methods=['GET'])
def admin_analytics():
    db = SessionLocal()
    try:
        # Basic Counts
        total_sessions = db.query(ChatSession).count()
        total_messages = db.query(ChatMessage).count()

        # Feedback Counts
        likes = db.query(Feedback).filter(Feedback.rating == 'like').count()
        dislikes = db.query(Feedback).filter(Feedback.rating == 'dislike').count()

        # Daily Chats Grouping (done in Python to avoid SQLite dialect issues)
        from collections import Counter
        from sqlalchemy import func
        sessions = db.query(ChatSession.start_time).all()
        daily_counts = Counter()
        for (start_time,) in sessions:
            if start_time:
                date_str = start_time.strftime('%Y-%m-%d')
                daily_counts[date_str] += 1

        # Average only over RAG bot replies with a measured duration (excludes FAQ and legacy zeros)
        avg_time = (
            db.query(func.avg(ChatMessage.generation_time))
            .filter(
                ChatMessage.role == 'bot',
                ChatMessage.generation_time.isnot(None),
                ChatMessage.generation_time > 0,
            )
            .scalar()
        )
        avg_time = float(avg_time) if avg_time is not None else 0.0

        unique_users = count_distinct_chat_users()

        return jsonify({
            'total_sessions': total_sessions,
            'total_messages': total_messages,
            'unique_users': unique_users,
            'likes': likes,
            'dislikes': dislikes,
            'daily_chats': dict(daily_counts),
            'avg_response_time': round(avg_time, 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/admin/chat-history', methods=['GET'])
def admin_chat_history():
    """Return recent chat sessions with messages and feedback (like/dislike) per message."""
    db = SessionLocal()
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(limit, 1), 200)
        sessions = (
            db.query(ChatSession)
            .order_by(ChatSession.start_time.desc())
            .limit(limit)
            .all()
        )
        out = []
        for sess in sessions:
            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == sess.session_id)
                .order_by(ChatMessage.timestamp.asc())
                .all()
            )
            msg_list = []
            for m in messages:
                fb = db.query(Feedback).filter(Feedback.message_id == m.id).order_by(Feedback.timestamp.desc()).first()
                msg_list.append({
                    'id': m.id,
                    'role': m.role,
                    'content': m.content,
                    'timestamp': m.timestamp.isoformat() + 'Z' if m.timestamp else None,
                    'feedback': fb.rating if fb else None,
                    'generation_time': round(m.generation_time, 2) if m.generation_time is not None else None,
                })
            last_ts = messages[-1].timestamp if messages else None
            _uid = (sess.user_id or '').strip()
            out.append({
                'session_id': sess.session_id,
                'user_id': _uid if _uid else None,
                'title': sess.title or "New Chat",
                'start_time': sess.start_time.isoformat() + 'Z' if sess.start_time else None,
                'last_message_time': last_ts.isoformat() + 'Z' if last_ts else None,
                'messages': msg_list,
            })
        return jsonify(out)
    finally:
        db.close()

@app.route('/load', methods=['POST'])
def load():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400

    original_filename = file.filename
    ext = os.path.splitext(original_filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            'error': 'Unsupported file type. Use .pdf, .docx, .txt, .csv, .xlsx, .xls, or .json'
        }), 400

    # Use original filename in uploads/ (sanitized; add (1),(2)... if duplicate)
    stored_name = make_unique_stored_name(original_filename)
    file_path = os.path.join(UPLOADS_DIR, stored_name)
    file.save(file_path)
    # Reject zero-byte files immediately before any DB/Chroma work
    if os.path.getsize(file_path) == 0:
        try:
            os.remove(file_path)
        except OSError:
            pass
        return jsonify({'error': 'الملف فارغ تماماً. يرجى اختيار ملف يحتوي على محتوى.'}), 422

    import hashlib
    from datetime import timedelta
    try:
        with open(file_path, "rb") as _fh:
            _content_hash = hashlib.sha256(_fh.read()).hexdigest()
    except OSError:
        _content_hash = None

    _now = datetime.utcnow()
    _abs_path = os.path.abspath(file_path)
    # Default lifecycle: valid 180 days; remind review at 160 days (before expiry)
    _default_valid_until = _now + timedelta(days=180)
    _default_next_review = _now + timedelta(days=160)

    # ── STEP 1: Write a DB record BEFORE touching Chroma ──────────────────
    # This makes every upload visible immediately and guarantees we always
    # have a row to update regardless of what happens during indexing.
    db = SessionLocal()
    try:
        record = FileRecord(
            filename=stored_name,
            file_path=_abs_path,
            original_filename=original_filename,
            chunk_count=0,
            content_hash=_content_hash,
            status="indexing",           # visible in admin panel immediately
            valid_until=_default_valid_until,
            next_review_at=_default_next_review,
        )
        db.add(record)
        db.commit()
        _record_id = record.id
    except Exception as e:
        db.rollback()
        db.close()
        try:
            os.remove(file_path)
        except OSError:
            pass
        return jsonify({'error': f'Database error before indexing: {e}'}), 500
    finally:
        db.close()

    # ── STEP 2: Index into Chroma ──────────────────────────────────────────
    # Any failure here is recoverable: the DB row exists with status='failed'
    # and the admin can retry reindexing without re-uploading the file.
    try:
        chunks = chatbot.load_documents(file_path)
    except Exception as e:
        # Clean up any partial Chroma writes for this filename
        try:
            chatbot.delete_file(stored_name)
        except Exception:
            pass
        # Mark the DB record as failed so the admin can see it and retry
        db2 = SessionLocal()
        try:
            row = db2.query(FileRecord).filter(FileRecord.id == _record_id).first()
            if row:
                row.status = "failed"
                db2.commit()
        except Exception:
            db2.rollback()
        finally:
            db2.close()
        return jsonify({
            'error': _friendly_chroma_error(e),
            'filename': stored_name,
            'record_id': _record_id,
            'hint': 'تم حفظ الملف. يمكنك إعادة محاولة الفهرسة من لوحة الإدارة.',
        }), 500

    # ── STEP 3: Validate we actually got chunks ────────────────────────────
    if chunks == 0:
        try:
            chatbot.delete_file(stored_name)
        except Exception:
            pass
        db3 = SessionLocal()
        try:
            row = db3.query(FileRecord).filter(FileRecord.id == _record_id).first()
            if row:
                row.status = "failed"
                db3.commit()
        except Exception:
            db3.rollback()
        finally:
            db3.close()
        return jsonify({
            'error': 'لم يتم استخراج أي نص من الملف. قد يكون يحتوي على صور فقط أو تالفاً.',
            'filename': stored_name,
            'record_id': _record_id,
            'hint': 'يمكن إعادة الفهرسة من لوحة الإدارة بعد التحقق من الملف.',
        }), 422

    # ── STEP 4: Commit the final 'active' state ────────────────────────────
    db4 = SessionLocal()
    try:
        row = db4.query(FileRecord).filter(FileRecord.id == _record_id).first()
        if row:
            row.status = "active"
            row.chunk_count = chunks
            db4.commit()
        create_document_version(
            file_record_id=_record_id,
            filename=stored_name,
            original_filename=original_filename,
            file_path=_abs_path,
            chunk_count=chunks,
            action="uploaded",
            content_hash=_content_hash,
        )
    except Exception:
        # Chroma already has the chunks; mark indexing so it's retryable.
        db4.rollback()
    finally:
        db4.close()

    return jsonify({
        'chunks': chunks,
        'filename': stored_name,
        'original_filename': original_filename,
        'valid_until': _default_valid_until.isoformat() + 'Z',
        'next_review_at': _default_next_review.isoformat() + 'Z',
    })


@app.route('/files', methods=['GET'])
def list_files():
    """Return all file records including validity/lifecycle fields."""
    db = SessionLocal()
    try:
        records = db.query(FileRecord).order_by(FileRecord.upload_date.desc()).all()

        def _iso(dt):
            return dt.isoformat() + 'Z' if dt else None

        return jsonify([
            {
                "id": r.id,
                "filename": r.filename,
                "original_filename": r.original_filename or r.filename,
                "upload_date": _iso(r.upload_date),
                "chunk_count": r.chunk_count,
                # Lifecycle / freshness fields
                "status": r.status or "active",
                "valid_until": _iso(r.valid_until),
                "next_review_at": _iso(r.next_review_at),
                "last_reviewed_at": _iso(r.last_reviewed_at),
                "owner": r.owner,
                "category": r.category,
                "source_url": r.source_url,
            }
            for r in records
        ])
    finally:
        db.close()


@app.route('/files/<path:filename>/download', methods=['GET'])
def download_file(filename):
    """Serve the original file from uploads/."""
    # Restrict to filename only (no path traversal)
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOADS_DIR, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(
        file_path,
        as_attachment=True,
        download_name=safe_name,
    )


@app.route('/files/<path:filename>/chunks', methods=['GET'])
def file_chunks(filename):
    """Return chunks stored in Chroma for this file (source metadata = filename)."""
    safe_name = os.path.basename(filename)
    try:
        chunks = chatbot.get_file_chunks(safe_name)
        return jsonify(chunks)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/files/<path:filename>', methods=['DELETE'])
def delete_file(filename):
    """Remove file from Chroma, from uploads/, and from SQLite."""
    safe_name = os.path.basename(filename)
    db = SessionLocal()
    try:
        record = db.query(FileRecord).filter(FileRecord.filename == safe_name).first()
        if not record:
            return jsonify({'error': 'File not found'}), 404
        file_path = record.file_path
        # 1) Delete chunks from Chroma
        try:
            chatbot.delete_file(safe_name)
        except Exception as e:
            return jsonify({'error': f'Failed to delete from vector store: {e}'}), 500
        # 2) Delete file from disk
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                return jsonify({'error': f'Failed to delete file: {e}'}), 500
        # 3) Delete record from DB
        db.delete(record)
        db.commit()
        return jsonify({'message': f'Deleted {safe_name}'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/admin/files/<int:record_id>/retire', methods=['POST'])
@require_admin
def api_file_retire(record_id):
    """
    Retire a static document:
      - Removes all Chroma chunks (document leaves the knowledge base immediately)
      - Sets status = 'retired' in Postgres (record kept for audit trail)
      - File stays on disk; it can be deleted separately via DELETE /files/<filename>

    This is the correct way to remove a document from chatbot answers without
    losing the history of what was once in the knowledge base.
    """
    db = SessionLocal()
    try:
        record = db.query(FileRecord).filter(FileRecord.id == record_id).first()
        if not record:
            return jsonify({'error': 'FileRecord not found'}), 404

        if record.status == 'retired':
            return jsonify({'ok': True, 'message': 'Already retired'}), 200

        filename = record.filename

        # Remove from Chroma so the chatbot stops using this document
        try:
            chatbot.delete_file(filename)
        except Exception as exc:
            return jsonify({'error': f'Failed to remove from vector store: {exc}'}), 500

        # Mark retired in Postgres (keep the record for audit trail)
        record.status = 'retired'
        record.chunk_count = 0

        # Audit entry
        create_document_version(
            file_record_id=record_id,
            filename=record.filename,
            original_filename=record.original_filename,
            file_path=record.file_path,
            chunk_count=0,
            action='retired',
            content_hash=record.content_hash,
            note='Retired by admin — removed from knowledge base',
        )
        db.commit()
        return jsonify({'ok': True, 'filename': filename})
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


@app.route('/api/admin/files/<int:record_id>/reindex', methods=['POST'])
@require_admin
def api_file_reindex(record_id):
    """
    Retry Chroma indexing for a file stuck in 'failed' or 'indexing' state.
    The file must still exist on disk.  Sets status → 'active' on success,
    keeps it as 'failed' if indexing fails again.
    """
    db = SessionLocal()
    try:
        record = db.query(FileRecord).filter(FileRecord.id == record_id).first()
        if not record:
            return jsonify({'error': 'FileRecord not found'}), 404
        if record.status not in ('failed', 'indexing'):
            return jsonify({'error': f'File status is "{record.status}" — only failed/indexing files need reindexing'}), 400
        if not os.path.isfile(record.file_path):
            record.status = 'failed'
            db.commit()
            return jsonify({'error': 'File no longer exists on disk. Delete this record and re-upload the file.', 'missing_path': record.file_path}), 404
        stored_name = record.filename
        file_path = record.file_path
    finally:
        db.close()

    # Clear any partial Chroma chunks from the previous attempt
    try:
        chatbot.delete_file(stored_name)
    except Exception:
        pass

    # Retry indexing
    try:
        chunks = chatbot.load_documents(file_path)
    except Exception as exc:
        db2 = SessionLocal()
        try:
            row = db2.query(FileRecord).filter(FileRecord.id == record_id).first()
            if row:
                row.status = 'failed'
                db2.commit()
        except Exception:
            db2.rollback()
        finally:
            db2.close()
        return jsonify({'error': _friendly_chroma_error(exc)}), 500

    if chunks == 0:
        db2 = SessionLocal()
        try:
            row = db2.query(FileRecord).filter(FileRecord.id == record_id).first()
            if row:
                row.status = 'failed'
                db2.commit()
        except Exception:
            db2.rollback()
        finally:
            db2.close()
        return jsonify({'error': 'File produced 0 chunks — it may be empty or unreadable.'}), 422

    db2 = SessionLocal()
    try:
        row = db2.query(FileRecord).filter(FileRecord.id == record_id).first()
        if row:
            row.status = 'active'
            row.chunk_count = chunks
            db2.commit()
        create_document_version(
            file_record_id=record_id,
            filename=stored_name,
            original_filename=record.original_filename,
            file_path=file_path,
            chunk_count=chunks,
            action='reindexed',
            content_hash=record.content_hash,
            note='Reindexed after previous failure',
        )
    except Exception:
        db2.rollback()
    finally:
        db2.close()

    return jsonify({'ok': True, 'chunk_count': chunks, 'filename': stored_name})


@app.route('/api/admin/files/<int:record_id>/restore', methods=['POST'])
@require_admin
def api_file_restore(record_id):
    """
    Restore a previously retired document back into the Chroma knowledge base.
    The file must still exist on disk (retire does not delete from disk).
    Sets status back to 'active'. Resets valid_until to now + 180 days when
    missing or past (same as upload). Resets overdue next_review_at to now + 160
    days (same as upload), capped at valid_until if that comes sooner.
    """
    from datetime import timedelta
    db = SessionLocal()
    try:
        record = db.query(FileRecord).filter(FileRecord.id == record_id).first()
        if not record:
            return jsonify({'error': 'FileRecord not found'}), 404

        if record.status != 'retired':
            return jsonify({'error': 'File is not retired — only retired files can be restored'}), 400

        file_path = record.file_path
        if not os.path.isfile(file_path):
            return jsonify({
                'error': 'File no longer exists on disk. Please re-upload it manually.',
                'missing_path': file_path,
            }), 404

        # Re-index into Chroma using the same load pipeline as a normal upload
        try:
            chunks = chatbot.load_documents(file_path)
        except Exception as exc:
            return jsonify({'error': f'Failed to re-index into vector store: {exc}'}), 500

        # Lifecycle: align with upload defaults (+180 valid, +160 review)
        _now = datetime.utcnow()
        record.status = 'active'
        record.chunk_count = chunks
        if not record.valid_until or record.valid_until < _now:
            record.valid_until = _now + timedelta(days=180)
        if not record.next_review_at or record.next_review_at < _now:
            review_candidate = _now + timedelta(days=160)
            vu = record.valid_until
            if vu and vu > _now:
                record.next_review_at = min(review_candidate, vu)
            else:
                record.next_review_at = review_candidate

        # Audit trail
        create_document_version(
            file_record_id=record_id,
            filename=record.filename,
            original_filename=record.original_filename,
            file_path=file_path,
            chunk_count=chunks,
            action='restored',
            content_hash=record.content_hash,
            note='Restored from retired state by admin',
        )
        db.commit()
        return jsonify({
            'ok': True,
            'filename': record.filename,
            'chunk_count': chunks,
            'status': 'active',
            'valid_until': record.valid_until.isoformat() + 'Z',
            'next_review_at': record.next_review_at.isoformat() + 'Z'
            if record.next_review_at
            else None,
        })
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


@app.route('/health', methods=['GET'])
def health():
    dynamic_sources = get_all_dynamic_sources()
    dynamic_summary = [
        {
            "id": s["id"],
            "name": s["name"],
            "source_type": s["source_type"],
            "status": s["status"],
            "is_enabled": s["is_enabled"],
            "endpoint_configured": bool(s.get("endpoint_url")),
            "last_sync_at": s.get("last_sync_at"),
        }
        for s in dynamic_sources
    ]
    return jsonify({
        "status": "ok",
        "llm_model": chatbot.llm_model,
        "embed_model": chatbot.embed_model,
        "persist_dir": chatbot.persist_dir,
        "vectorstore_loaded": chatbot.vectorstore is not None,
        "dynamic_sources": dynamic_summary,
        "dynamic_sources_count": len(dynamic_sources),
        "dynamic_sources_ok": sum(1 for s in dynamic_sources if s["status"] == "ok"),
    })


# =============================================================================
# Admin REST API (JWT-protected) — consumed by the React admin panel
# =============================================================================

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    db = SessionLocal()
    try:
        user = verify_admin_login(db, username, password)
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        token = _make_jwt(user.username, user.role or 'admin')
        return jsonify({'token': token, 'username': user.username, 'role': user.role})
    finally:
        db.close()


@app.route('/api/admin/me', methods=['GET'])
@require_admin
def api_admin_me():
    auth = request.headers.get('Authorization', '')
    token = auth[len('Bearer '):]
    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    return jsonify({'username': payload.get('sub'), 'role': payload.get('role')})


# --- FAQs ---

@app.route('/api/admin/faqs', methods=['GET'])
@require_admin
def api_faqs_list():
    return jsonify(get_all_faqs())


@app.route('/api/admin/faqs', methods=['POST'])
@require_admin
def api_faqs_add():
    data = request.json or {}
    ok, err = add_faq(data.get('question', ''), data.get('answer', ''))
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True}), 201


@app.route('/api/admin/faqs/normalize', methods=['POST'])
@require_admin
def api_faqs_normalize():
    ok, err = normalize_faq_order()
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True})


@app.route('/api/admin/faqs/<int:faq_id>', methods=['PUT'])
@require_admin
def api_faqs_update(faq_id):
    data = request.json or {}
    ok, err = update_faq(
        faq_id,
        data.get('question', ''),
        data.get('answer', ''),
        data.get('display_order'),
    )
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True})


@app.route('/api/admin/faqs/<int:faq_id>', methods=['DELETE'])
@require_admin
def api_faqs_delete(faq_id):
    ok, err = delete_faq(faq_id)
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True})


# --- Manual Overrides ---

@app.route('/api/admin/overrides', methods=['GET'])
@require_admin
def api_overrides_list():
    return jsonify(get_all_overrides())


@app.route('/api/admin/overrides', methods=['POST'])
@require_admin
def api_overrides_add():
    data = request.json or {}
    ok, err = add_override(data.get('trigger_phrase', ''), data.get('answer', ''))
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True}), 201


@app.route('/api/admin/overrides/<int:override_id>', methods=['PUT'])
@require_admin
def api_overrides_update(override_id):
    data = request.json or {}
    ok, err = update_override(override_id, data.get('trigger_phrase', ''), data.get('answer', ''))
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True})


@app.route('/api/admin/overrides/<int:override_id>', methods=['DELETE'])
@require_admin
def api_overrides_delete(override_id):
    ok, err = delete_override(override_id)
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True})


# --- System Settings ---

@app.route('/api/admin/settings', methods=['GET'])
@require_admin
def api_settings_get():
    return jsonify({key: get_setting(key) for key in ADMIN_SETTING_KEYS})


@app.route('/api/admin/settings', methods=['PUT'])
@require_admin
def api_settings_update():
    data = request.json or {}
    failed = []
    for key in ADMIN_SETTING_KEYS:
        if key in data:
            if not update_setting(key, data[key]):
                failed.append(key)
    if failed:
        return jsonify({'error': f'Failed to update: {failed}'}), 500
    return jsonify({'ok': True})


@app.route('/api/admin/settings/restore', methods=['POST'])
@require_admin
def api_settings_restore():
    if not restore_default_settings():
        return jsonify({'error': 'Failed to restore defaults'}), 500
    return jsonify({'ok': True})


# --- Unanswered Queries ---

@app.route('/api/admin/unanswered', methods=['GET'])
@require_admin
def api_unanswered_list():
    rows = get_unanswered_queries()
    # Convert datetime objects to strings for JSON serialisation
    out = []
    for row in rows:
        r = dict(row)
        ts = r.get('timestamp')
        if ts and hasattr(ts, 'isoformat'):
            r['timestamp'] = ts.isoformat() + 'Z'
        out.append(r)
    return jsonify(out)


@app.route('/api/admin/unanswered/<int:query_id>/resolve', methods=['PUT'])
@require_admin
def api_unanswered_resolve(query_id):
    ok = mark_query_resolved(query_id)
    if not ok:
        return jsonify({'error': 'Query not found'}), 404
    return jsonify({'ok': True})


@app.route('/api/admin/unanswered/resolve-all', methods=['POST'])
@require_admin
def api_unanswered_resolve_all():
    """
    Mark pending unanswered queries as resolved.
    Optional JSON body: { "reason": "<exact reason string>" } — if omitted, all pending rows.
    """
    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip() or None
    ok, n = mark_all_pending_queries_resolved(reason_filter=reason)
    if not ok:
        return jsonify({'error': 'Failed to update queries'}), 500
    return jsonify({'ok': True, 'resolved': n})


# =============================================================================
# Static file lifecycle routes (JWT-protected)
# =============================================================================

@app.route('/api/admin/files/stale', methods=['GET'])
@require_admin
def api_files_stale():
    """Return files that are stale, past their valid_until, or overdue for review."""
    return jsonify(get_stale_files())


@app.route('/api/admin/files/<int:record_id>/versions', methods=['GET'])
@require_admin
def api_file_versions(record_id):
    """Return the audit / version history for a static file."""
    return jsonify(get_document_versions(record_id))


@app.route('/api/admin/files/<int:record_id>/freshness', methods=['PUT'])
@require_admin
def api_file_freshness(record_id):
    """
    Update freshness / lifecycle metadata on a static FileRecord.
    Body (all optional):
      source_url, owner, category, valid_from, valid_until, next_review_at, status
    """
    data = request.json or {}

    def _parse_dt(key):
        val = (data.get(key) or "").strip()
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.rstrip("Z"))
        except ValueError:
            return None

    ok, err = update_file_freshness(
        record_id,
        source_url=data.get("source_url"),
        owner=data.get("owner"),
        category=data.get("category"),
        valid_from=_parse_dt("valid_from"),
        valid_until=_parse_dt("valid_until"),
        next_review_at=_parse_dt("next_review_at"),
        status=data.get("status"),
    )
    if not ok:
        return jsonify({'error': err}), 404 if "not found" in (err or "").lower() else 400
    return jsonify({'ok': True})


@app.route('/api/admin/files/<int:record_id>/review', methods=['PUT'])
@require_admin
def api_file_mark_reviewed(record_id):
    """Mark a file as reviewed (sets last_reviewed_at = now, status = active)."""
    data = request.json or {}
    note = (data.get("note") or "").strip() or None
    ok, err = mark_file_reviewed(record_id, note=note)
    if not ok:
        return jsonify({'error': err}), 404 if "not found" in (err or "").lower() else 400
    return jsonify({'ok': True})


@app.route('/api/admin/files/<int:record_id>/replace', methods=['PUT'])
@require_admin
def api_file_replace(record_id):
    """
    Replace the content of an existing static file without changing its record id.

    Multipart body: file=<new file upload>
    Optional JSON fields: note (string)

    Process:
      1. Validate the new file type.
      2. Save the new file to uploads/ with a fresh stored name.
      3. Call chatbot.replace_file(old_filename, new_path, new_name)
         which atomically deletes old Chroma chunks and indexes the new ones.
      4. Update FileRecord with new path, filename, chunk_count, content_hash.
      5. Append a DocumentVersion row for audit trail.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    db = SessionLocal()
    try:
        record = db.query(FileRecord).filter(FileRecord.id == record_id).first()
        if not record:
            return jsonify({'error': 'FileRecord not found'}), 404

        old_filename = record.filename
        old_file_path = record.file_path

        new_file = request.files['file']
        if not new_file.filename:
            return jsonify({'error': 'Empty filename'}), 400

        original_filename = new_file.filename
        ext = os.path.splitext(original_filename.lower())[1]
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({'error': f'Unsupported file type: {ext}'}), 400

        # Save new file
        new_stored_name = make_unique_stored_name(original_filename)
        new_file_path = os.path.join(UPLOADS_DIR, new_stored_name)
        new_file.save(new_file_path)

        # Compute content hash of new file
        import hashlib
        try:
            with open(new_file_path, "rb") as fh:
                new_hash = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            new_hash = None

        # ── Pre-flight: reject empty files before touching Chroma ──────────
        if os.path.getsize(new_file_path) == 0:
            try:
                os.remove(new_file_path)
            except OSError:
                pass
            return jsonify({'error': 'الملف الجديد فارغ تماماً. يرجى اختيار ملف يحتوي على محتوى.'}), 422

        # ── Step 1: Index NEW file first (safe — old chunks untouched) ──────
        # load_documents() uses basename(new_file_path) as source key in Chroma,
        # so new and old chunks coexist briefly without interfering.
        try:
            new_chunks = chatbot.load_documents(new_file_path)
        except Exception as exc:
            try:
                os.remove(new_file_path)
            except OSError:
                pass
            friendly = _friendly_chroma_error(exc)
            return jsonify({'error': friendly}), 500

        if new_chunks == 0:
            # File was parseable but contained no usable text (images-only PDF etc.)
            try:
                chatbot.delete_file(new_stored_name)
            except Exception:
                pass
            try:
                os.remove(new_file_path)
            except OSError:
                pass
            return jsonify({'error': 'لم يتم استخراج أي نص من الملف الجديد. قد يكون الملف يحتوي على صور فقط أو تالفاً. الملف القديم لا يزال موجوداً.'}), 422

        # ── Step 2: Remove OLD chunks now that new ones are confirmed ────────
        try:
            chatbot.delete_file(old_filename)
        except Exception as exc:
            # Non-fatal: log and continue; old chunks may linger but new are live
            app.logger.warning("replace: could not delete old chunks for %r: %s", old_filename, exc)

        # ── Step 3: Clean up old file from disk ──────────────────────────────
        if old_file_path and os.path.isfile(old_file_path) and old_file_path != new_file_path:
            try:
                os.remove(old_file_path)
            except OSError:
                pass

        # ── Step 4: Audit + update DB ────────────────────────────────────────
        note = (request.form.get('note') or '').strip() or None
        create_document_version(
            file_record_id=record_id,
            filename=old_filename,
            original_filename=record.original_filename,
            file_path=old_file_path,
            chunk_count=record.chunk_count,
            action='replaced',
            content_hash=record.content_hash,
            note=f"Replaced by {original_filename}. {note or ''}".strip(),
        )

        record.filename = new_stored_name
        record.file_path = os.path.abspath(new_file_path)
        record.original_filename = original_filename
        record.chunk_count = new_chunks
        record.content_hash = new_hash
        record.upload_date = datetime.utcnow()
        record.status = 'active'
        db.commit()

        return jsonify({
            'ok': True,
            'filename': new_stored_name,
            'original_filename': original_filename,
            'chunks': new_chunks,
        })
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# =============================================================================
# Dynamic source admin routes (JWT-protected)
# =============================================================================

@app.route('/api/admin/dynamic-sources', methods=['GET'])
@require_admin
def api_dynamic_sources_list():
    """List all configured dynamic data sources."""
    return jsonify(get_all_dynamic_sources())


@app.route('/api/admin/dynamic-sources', methods=['POST'])
@require_admin
def api_dynamic_sources_create():
    """
    Create a new DynamicSource configuration.
    Body: { name, source_type, endpoint_url?, sync_frequency?, is_enabled?,
            schedule_type?, sync_times?, schedule_day?, schedule_month_day? }
    """
    data = request.json or {}
    source_id, err = create_dynamic_source(
        name=data.get('name', ''),
        source_type=data.get('source_type', ''),
        endpoint_url=data.get('endpoint_url'),
        sync_frequency=data.get('sync_frequency', 'manual'),
        is_enabled=bool(data.get('is_enabled', True)),
        auth_token=data.get('auth_token'),
        schedule_type=data.get('schedule_type', 'manual'),
        sync_times=data.get('sync_times'),
        schedule_day=data.get('schedule_day'),
        schedule_month_day=data.get('schedule_month_day'),
    )
    if source_id is None:
        return jsonify({'error': err}), 400
    source = get_dynamic_source(source_id)
    # Register scheduler jobs for this new source
    _schedule_source(source)
    return jsonify(source), 201


@app.route('/api/admin/dynamic-sources/<int:source_id>', methods=['PUT'])
@require_admin
def api_dynamic_sources_update(source_id):
    """Update an existing DynamicSource configuration."""
    data = request.json or {}
    is_enabled = data.get('is_enabled')
    ok, err = update_dynamic_source(
        source_id,
        name=data.get('name'),
        source_type=data.get('source_type'),
        endpoint_url=data.get('endpoint_url'),
        sync_frequency=data.get('sync_frequency'),
        is_enabled=None if is_enabled is None else bool(is_enabled),
        auth_token=data.get('auth_token'),
        schedule_type=data.get('schedule_type'),
        sync_times=data.get('sync_times'),
        schedule_day=data.get('schedule_day'),
        schedule_month_day=data.get('schedule_month_day'),
    )
    if not ok:
        return jsonify({'error': err}), 404 if "not found" in (err or "").lower() else 400
    source = get_dynamic_source(source_id)
    # Re-register scheduler jobs with the updated config
    _schedule_source(source)
    return jsonify(source)


@app.route('/api/admin/dynamic-sources/<int:source_id>', methods=['DELETE'])
@require_admin
def api_dynamic_sources_delete(source_id):
    """
    Delete a DynamicSource, its sync run history, and its Chroma chunks.
    Chroma cleanup happens first so we still have the source_type available.
    """
    source = get_dynamic_source(source_id)
    if source is None:
        return jsonify({'error': 'DynamicSource not found'}), 404

    # Remove all scheduled jobs for this source
    _remove_source_jobs(source_id)

    # Remove indexed chunks from Chroma before touching the DB row
    chroma_key = f"dynamic_{source['source_type']}_{source_id}"
    try:
        ingestion_service._delete_source_chunks(chroma_key)
        logger.info("Deleted Chroma chunks for source %s (%s) on source deletion", source_id, chroma_key)
    except Exception as exc:
        logger.warning("Could not delete Chroma chunks for %s during source deletion: %s", chroma_key, exc)

    ok, err = delete_dynamic_source(source_id)
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True, 'chroma_key_purged': chroma_key})


@app.route('/api/admin/dynamic-sources/<int:source_id>/sync', methods=['POST'])
@require_admin
def api_dynamic_sources_sync(source_id):
    """
    Trigger a manual sync for the given DynamicSource.

    Runs synchronously in the request thread (Phase 1: manual sync).
    For sources that are not yet configured this returns a clear status
    message rather than an error, so the admin UI can show a helpful prompt.
    """
    result = ingestion_service.sync_source(source_id)
    status_code = 200 if result.get('ok') else 422
    return jsonify(result), status_code


@app.route('/api/admin/dynamic-sources/<int:source_id>/runs', methods=['GET'])
@require_admin
def api_dynamic_sources_runs(source_id):
    """Return recent sync run history for a DynamicSource (newest first, max 20)."""
    limit = min(int(request.args.get('limit', 20)), 100)
    return jsonify(get_sync_runs(source_id, limit=limit))


@app.route('/api/admin/dynamic-sources/<int:source_id>/chunks', methods=['GET'])
@require_admin
def api_dynamic_source_chunks(source_id):
    """
    Return the Chroma chunks currently indexed for a dynamic source.
    The Chroma source key is: dynamic_{source_type}_{source_id}
    """
    source = get_dynamic_source(source_id)
    if not source:
        return jsonify({'error': 'DynamicSource not found'}), 404

    chroma_key = f"dynamic_{source['source_type']}_{source_id}"
    try:
        chunks = chatbot.get_file_chunks(chroma_key)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    return jsonify({'chroma_key': chroma_key, 'chunks': chunks})


@app.route('/api/admin/llm-config', methods=['GET'])
@require_admin
def api_get_llm_config():
    """Return current LLM configuration. API key is never returned — only whether it is set."""
    from database import get_llm_config
    cfg = get_llm_config()
    return jsonify({
        "provider":     cfg.get("llm_provider", "ollama"),
        "api_base_url": cfg.get("llm_api_base_url", ""),
        "model_name":   cfg.get("llm_model_name", ""),
        "api_key_set":  bool(cfg.get("llm_api_key", "").strip()),
    })


@app.route('/api/admin/llm-config', methods=['PUT'])
@require_admin
def api_put_llm_config():
    """Save LLM configuration and hot-reload the LLM — no Flask restart needed."""
    from database import save_llm_config
    body = request.get_json(silent=True) or {}
    provider     = str(body.get("provider", "ollama")).strip().lower()
    api_base_url = str(body.get("api_base_url", "")).strip()
    api_key      = str(body.get("api_key", "")).strip()     # empty = keep existing
    model_name   = str(body.get("model_name", "")).strip()

    if provider not in ("ollama", "openai_compatible"):
        return jsonify({"error": "provider must be 'ollama' or 'openai_compatible'"}), 400

    ok = save_llm_config(provider, api_base_url, api_key, model_name)
    if not ok:
        return jsonify({"error": "Failed to save config to database"}), 500

    # Hot-reload — the chatbot instance is global in rag_api.py
    summary = chatbot.reload_llm()
    return jsonify({"ok": True, **summary})


@app.route('/api/admin/llm-config/test', methods=['GET'])
@require_admin
def api_test_llm_config():
    """
    Send a minimal Arabic prompt to the configured LLM and return the result.
    Used by the admin panel "Test Connection" button.
    """
    import time
    test_prompt = "أجب بجملة واحدة فقط: ما هي عاصمة فلسطين؟"
    t0 = time.time()
    try:
        response = chatbot._llm_invoke(test_prompt)
        latency_ms = int((time.time() - t0) * 1000)
        preview = (response or "").strip()[:200]
        return jsonify({
            "ok": True,
            "response_preview": preview,
            "latency_ms": latency_ms,
            "provider": chatbot._llm_provider,
            "model": chatbot._llm_model_name,
        })
    except Exception as exc:
        latency_ms = int((time.time() - t0) * 1000)
        return jsonify({
            "ok": False,
            "error": str(exc),
            "latency_ms": latency_ms,
            "provider": chatbot._llm_provider,
            "model": chatbot._llm_model_name,
        }), 200   # always 200 so the frontend can read the body


@app.route('/api/admin/tool-routing/status', methods=['GET'])
@require_admin
def api_tool_routing_status():
    """
    Return the current tool-routing configuration and a live connectivity
    ping to the three mock university API endpoints.
    """
    provider = (os.getenv("LLM_PROVIDER") or "ollama").strip().lower()
    tools_enabled = provider == "openai_compatible"

    mock_base = "http://localhost:5001"

    # Obtain a bearer token (env var first, then fresh from /auth/token)
    token = (os.getenv("MOCK_API_TOKEN") or "").strip()
    if not token:
        try:
            r = requests.post(
                f"{mock_base}/auth/token",
                json={"username": "hebron_api", "password": "test1234"},
                timeout=3,
            )
            if r.ok:
                token = r.json().get("access_token", "")
        except Exception:
            pass

    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    endpoints = {
        "calendar":      f"{mock_base}/api/calendar",
        "announcements": f"{mock_base}/api/announcements",
        "admissions":    f"{mock_base}/api/admissions",
        "fees":          f"{mock_base}/api/fees",
        "faculty":       f"{mock_base}/api/faculty",
    }

    connectivity: dict = {}
    for name, url in endpoints.items():
        try:
            resp = requests.get(url, headers=auth_headers, timeout=3)
            connectivity[name] = {"reachable": resp.ok, "status_code": resp.status_code}
        except requests.ConnectionError:
            connectivity[name] = {"reachable": False, "error": "connection refused"}
        except Exception as exc:
            connectivity[name] = {"reachable": False, "error": str(exc)}

    return jsonify({
        "llm_provider": provider,
        "tools_enabled": tools_enabled,
        "mock_api_base": mock_base,
        "mock_api_connectivity": connectivity,
    })


@app.route('/api/admin/scheduler/jobs', methods=['GET'])
@require_admin
def api_scheduler_jobs():
    """
    Return a list of all currently scheduled auto-sync jobs.
    Each entry: { job_id, source_id, source_name, next_run_time, cron_expression }
    """
    sources_by_id = {s['id']: s for s in get_all_dynamic_sources()}
    jobs_out = []
    for job in _scheduler.get_jobs():
        if not job.id.startswith("sync_"):
            continue
        parts = job.id.split("_")
        try:
            src_id = int(parts[1])
        except (IndexError, ValueError):
            src_id = None
        src_name = sources_by_id.get(src_id, {}).get("name", "—") if src_id else "—"
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        jobs_out.append({
            "job_id": job.id,
            "source_id": src_id,
            "source_name": src_name,
            "next_run_time": next_run,
            "trigger": str(job.trigger),
        })
    jobs_out.sort(key=lambda j: (j["source_id"] or 0, j["job_id"]))
    return jsonify({"jobs": jobs_out, "total": len(jobs_out)})


# --- Serve React admin SPA (production build) ---

@app.route('/admin-panel/')
@app.route('/admin-panel/<path:path>')
def serve_admin_panel(path=''):
    static_dir = os.path.join(BASE_DIR, 'admin-panel', 'dist')
    if not os.path.isdir(static_dir):
        return jsonify({'error': 'Admin panel not built. Run: cd admin-panel && npm run build'}), 503
    file_path = os.path.join(static_dir, path)
    if path and os.path.isfile(file_path):
        return send_file(file_path)
    return send_file(os.path.join(static_dir, 'index.html'))


# ---------------------------------------------------------------------------
# Widget static-file routes
# ---------------------------------------------------------------------------
WIDGET_DIR = os.path.join(BASE_DIR, "widget")


@app.route("/widget/", strict_slashes=False)
def widget_index():
    """Serve the standalone test/iframe page."""
    return send_file(os.path.join(WIDGET_DIR, "index.html"))


@app.route("/widget/widget.css")
def widget_css():
    return send_file(os.path.join(WIDGET_DIR, "widget.css"), mimetype="text/css")


@app.route("/widget/widget.js")
def widget_js():
    return send_file(
        os.path.join(WIDGET_DIR, "widget.js"),
        mimetype="application/javascript",
    )


@app.route("/widget/config")
def widget_config():
    """
    Public runtime config consumed by widget.js.

    Returns JSON:
      {
        "bot_logo_b64":    "<base64 PNG string> | null",
        "campus_map_b64":  "<base64 JPEG/PNG string> | null",
        "campus_map_mime": "image/jpeg" | "image/png" | null,
        "map_icon_b64":    "<base64 JPEG string> | null",
        "map_icon_mime":   "image/jpeg" | null,
        "faq_items":       [ {id, question, answer, order_index}, ... ]
      }

    The widget may also pass campus_map_url if the image is served as a
    static asset (not yet implemented here — b64 is simpler for now).
    """

    def _guess_mime(p: str) -> str:
        ext = os.path.splitext(p)[1].lower()
        if ext in (".jpg", ".jpeg", ".jfif", ".jepg"):
            return "image/jpeg"
        if ext == ".webp":
            return "image/webp"
        if ext == ".gif":
            return "image/gif"
        return "image/png"

    # --- bot logo ---
    logo_b64 = None
    logo_path = os.path.join(BASE_DIR, "assets", "logo.png")
    if os.path.isfile(logo_path):
        try:
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode()
        except Exception:
            pass

    # --- campus map ---
    map_b64 = None
    map_mime = None
    map_candidates = [
        os.path.join(BASE_DIR, "assets", "campus_map.png"),
        os.path.join(BASE_DIR, "assets", "campus_map.jpg"),
        os.path.join(BASE_DIR, "assets", "campus_map.jpeg"),
        os.path.join(BASE_DIR, "assets", "hebron_map.jepg"),
        os.path.join(BASE_DIR, "assets", "hebron_map.jpeg"),
        os.path.join(BASE_DIR, "assets", "hebron_map.jpg"),
        os.path.join(BASE_DIR, "assets", "hebron_map.png"),
    ]
    for candidate in map_candidates:
        if os.path.isfile(candidate):
            try:
                with open(candidate, "rb") as f:
                    map_b64 = base64.b64encode(f.read()).decode()
                map_mime = _guess_mime(candidate)
                break
            except Exception:
                pass

    # --- map button icon ---
    map_icon_b64 = None
    map_icon_mime = None
    map_icon_path = os.path.join(BASE_DIR, "assets", "map-symbol.png")
    if os.path.isfile(map_icon_path):
        try:
            with open(map_icon_path, "rb") as f:
                map_icon_b64 = base64.b64encode(f.read()).decode()
            map_icon_mime = _guess_mime(map_icon_path)
        except Exception:
            pass

    # --- FAQs ---
    faq_rows = get_all_faqs()

    return jsonify(
        {
            "bot_logo_b64": logo_b64,
            "campus_map_b64": map_b64,
            "campus_map_mime": map_mime,
            "map_icon_b64": map_icon_b64,
            "map_icon_mime": map_icon_mime,
            "faq_items": faq_rows if isinstance(faq_rows, list) else [],
        }
    )


if __name__ == '__main__':
    try:
        from waitress import serve
        logger.info("Starting with waitress on %s:%s (threads=8)", RAG_API_HOST, RAG_API_PORT)
        serve(app, host=RAG_API_HOST, port=RAG_API_PORT, threads=8)
    except ImportError:
        logger.warning("waitress not installed — using Flask dev server with threading enabled")
        app.run(host=RAG_API_HOST, port=RAG_API_PORT, debug=False, threaded=True)