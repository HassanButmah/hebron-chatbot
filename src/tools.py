"""
LangChain tools for Hebron University live data.

Each tool calls the mock REST API server (port 5001) and returns a
formatted Arabic string ready to be injected as context.

Token strategy:
  1. Use MOCK_API_TOKEN from the environment if set.
  2. Otherwise, obtain a fresh JWT by posting credentials to /auth/token.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

logger = logging.getLogger(__name__)

_MOCK_BASE = "http://localhost:5001"
_CREDS = {"username": "hebron_api", "password": "test1234"}
_TIMEOUT = 8  # seconds


def _get_token() -> str:
    """Return a valid bearer token; prefer the env var, fall back to /auth/token."""
    token = os.getenv("MOCK_API_TOKEN", "").strip()
    if token:
        return token
    try:
        resp = requests.post(
            f"{_MOCK_BASE}/auth/token",
            json=_CREDS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("access_token", "")
    except Exception as exc:
        logger.warning("Could not obtain mock API token: %s", exc)
        return ""


def _get_json(path: str) -> Any:
    """Authenticated GET; returns parsed JSON or raises."""
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.get(f"{_MOCK_BASE}{path}", headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _format_events(events: list[dict]) -> str:
    lines = []
    for ev in events:
        title = ev.get("title") or ev.get("event") or ev.get("name") or str(ev)
        date = ev.get("date") or ev.get("start_date") or ""
        end_date = ev.get("end_date") or ""
        desc = ev.get("description") or ""
        line = f"• {title}"
        if date:
            line += f" — {date}"
            if end_date and end_date != date:
                line += f" حتى {end_date}"
        if desc:
            line += f"\n  {desc}"
        lines.append(line)
    return "\n".join(lines) if lines else "لا توجد أحداث متاحة حالياً."


def _format_announcements(items: list[dict]) -> str:
    lines = []
    for item in items:
        title = item.get("title") or item.get("subject") or str(item)
        date = item.get("date") or item.get("published_at") or ""
        body = item.get("body") or item.get("content") or item.get("description") or ""
        line = f"• {title}"
        if date:
            line += f" ({date})"
        if body:
            line += f"\n  {body}"
        lines.append(line)
    return "\n".join(lines) if lines else "لا توجد إعلانات متاحة حالياً."


def _format_faculty(members: list[dict]) -> str:
    if not members:
        return "لم يتم العثور على أعضاء هيئة تدريس مطابقين للبحث."
    lines = []
    for m in members:
        name = m.get("name") or m.get("name_en") or str(m)
        title = m.get("title") or ""
        college = m.get("college") or ""
        department = m.get("department") or ""
        role = m.get("role") or ""
        specialization = m.get("specialization") or ""
        email = m.get("email") or ""
        office_hours = m.get("office_hours") or ""

        line = f"• {title} {name}".strip()
        if role:
            line += f" — {role}"
        if college:
            line += f"\n  الكلية: {college}"
        if department:
            line += f" | القسم: {department}"
        if specialization:
            line += f"\n  التخصص: {specialization}"
        if office_hours:
            line += f"\n  ساعات المكتب: {office_hours}"
        if email:
            line += f"\n  البريد: {email}"
        lines.append(line)
    return "\n\n".join(lines)


def _format_fees(items: list[dict]) -> str:
    lines = []
    for item in items:
        fee_type = item.get("fee_type") or item.get("name") or str(item)
        fee_type_en = item.get("fee_type_en") or ""
        amount = item.get("amount_jod") or item.get("amount") or ""
        currency = item.get("currency") or "JOD"
        timing = item.get("payment_timing") or ""
        notes = item.get("notes") or ""

        line = f"• {fee_type}"
        if fee_type_en:
            line += f" ({fee_type_en})"
        if amount:
            line += f": {amount} {currency}"
        if timing:
            line += f" — {timing}"
        if notes:
            line += f"\n  {notes}"
        lines.append(line)
    return "\n".join(lines) if lines else "لا تتوفر معلومات عن الرسوم حالياً."


def _format_admissions(data: Any) -> str:
    if isinstance(data, list):
        lines = []
        for item in data:
            prog = item.get("program") or item.get("name") or str(item)
            deadline = item.get("deadline") or item.get("date") or ""
            desc = item.get("description") or item.get("requirements") or ""
            line = f"• {prog}"
            if deadline:
                line += f" — الموعد النهائي: {deadline}"
            if desc:
                line += f"\n  {desc}"
            lines.append(line)
        return "\n".join(lines) if lines else "لا توجد معلومات قبول متاحة."
    if isinstance(data, dict):
        parts = []
        for k, v in data.items():
            parts.append(f"{k}: {v}")
        return "\n".join(parts)
    return str(data)


# ── Tool definitions ──────────────────────────────────────────────────────────

@tool
def get_university_calendar() -> str:
    """
    Fetch upcoming events from the Hebron University academic calendar.
    Returns a formatted Arabic list of upcoming events with dates.
    """
    try:
        data = _get_json("/api/calendar")
        events = data if isinstance(data, list) else data.get("events") or data.get("data") or []
        header = "📅 التقويم الأكاديمي — الأحداث القادمة:\n"
        return header + _format_events(events)
    except requests.ConnectionError:
        logger.warning("Mock API server is not running (calendar)")
        return "عذراً، تعذر الاتصال بخادم بيانات التقويم الجامعي. يرجى التأكد من تشغيل الخادم."
    except requests.HTTPError as exc:
        logger.warning("Calendar API HTTP error: %s", exc)
        return "عذراً، حدث خطأ أثناء جلب بيانات التقويم الجامعي."
    except Exception as exc:
        logger.error("Unexpected calendar tool error: %s", exc)
        return "عذراً، حدث خطأ غير متوقع أثناء جلب بيانات التقويم."


@tool
def get_announcements() -> str:
    """
    Fetch the latest announcements and news from Hebron University.
    Returns a formatted Arabic list of recent announcements.
    """
    try:
        data = _get_json("/api/announcements")
        items = data if isinstance(data, list) else data.get("announcements") or data.get("data") or []
        header = "📢 إعلانات جامعة الخليل الأخيرة:\n"
        return header + _format_announcements(items)
    except requests.ConnectionError:
        logger.warning("Mock API server is not running (announcements)")
        return "عذراً، تعذر الاتصال بخادم بيانات الإعلانات. يرجى التأكد من تشغيل الخادم."
    except requests.HTTPError as exc:
        logger.warning("Announcements API HTTP error: %s", exc)
        return "عذراً، حدث خطأ أثناء جلب بيانات الإعلانات."
    except Exception as exc:
        logger.error("Unexpected announcements tool error: %s", exc)
        return "عذراً، حدث خطأ غير متوقع أثناء جلب بيانات الإعلانات."


@tool
def get_faculty_info(query: str) -> str:
    """
    Search for faculty members, professors, doctors, or staff at Hebron University.
    Use this tool for ANY question about a professor, doctor, lecturer, dean, or department head —
    including their office hours (ساعات المكتب / ساعات مكتبية), email, role, college, or department.
    Extract the person's name or department from the user's question and pass it as `query`.
    Examples:
      query="نبيل حساسنة"  (searching by name)
      query="كلية تكنولوجيا المعلومات"  (searching by college)
      query="قسم الرياضيات"  (searching by department)
      query="خليل مصري"  (searching by name)
    Returns name, title, role, college, department, office hours, and email.
    """
    try:
        import urllib.parse
        import re as _re
        # Guard: if the LLM accidentally passes the full question, strip common
        # noise words so the server's token matcher still finds the right person.
        noise = r"\b(what|is|are|the|his|her|their|of|for|about|in|at|and|office|hours|email|college|department|role|who|tell|me|dr\.?|prof\.?)\b"
        cleaned = _re.sub(noise, " ", query, flags=_re.IGNORECASE).strip()
        # If cleaning wiped everything, fall back to original query
        search_term = cleaned if len(cleaned) > 2 else query
        encoded = urllib.parse.quote(search_term)
        logger.info("Faculty tool search term: %r (from query: %r)", search_term, query)
        data = _get_json(f"/api/faculty?search={encoded}")
        members = data if isinstance(data, list) else data.get("faculty") or data.get("data") or []
        header = f"👨‍🏫 نتائج البحث عن \"{query}\" في دليل أعضاء هيئة التدريس:\n"
        return header + _format_faculty(members)
    except requests.ConnectionError:
        logger.warning("Mock API server is not running (faculty)")
        return "عذراً، تعذر الاتصال بخادم بيانات أعضاء هيئة التدريس. يرجى التأكد من تشغيل الخادم."
    except requests.HTTPError as exc:
        logger.warning("Faculty API HTTP error: %s", exc)
        return "عذراً، حدث خطأ أثناء جلب بيانات أعضاء هيئة التدريس."
    except Exception as exc:
        logger.error("Unexpected faculty tool error: %s", exc)
        return "عذراً، حدث خطأ غير متوقع أثناء البحث عن أعضاء هيئة التدريس."


@tool
def get_financial_info() -> str:
    """
    Fetch the university fee schedule from Hebron University.
    Returns a formatted Arabic list of all fee types with amounts in Jordanian Dinar (JOD).
    Use this tool when the user asks about tuition fees, registration fees,
    insurance fees, application fees, or any other university charges.
    """
    try:
        data = _get_json("/api/fees")
        items = data if isinstance(data, list) else data.get("fees") or data.get("data") or []
        header = "💰 جدول الرسوم الجامعية — جامعة الخليل (بالدينار الأردني):\n"
        return header + _format_fees(items)
    except requests.ConnectionError:
        logger.warning("Mock API server is not running (fees)")
        return "عذراً، تعذر الاتصال بخادم بيانات الرسوم الجامعية. يرجى التأكد من تشغيل الخادم."
    except requests.HTTPError as exc:
        logger.warning("Fees API HTTP error: %s", exc)
        return "عذراً، حدث خطأ أثناء جلب بيانات الرسوم الجامعية."
    except Exception as exc:
        logger.error("Unexpected fees tool error: %s", exc)
        return "عذراً، حدث خطأ غير متوقع أثناء جلب بيانات الرسوم."


@tool
def get_admissions_info() -> str:
    """
    Fetch admission deadlines and registration information from Hebron University.
    Returns a formatted Arabic summary of admission requirements and deadlines.
    """
    try:
        data = _get_json("/api/admissions")
        header = "🎓 معلومات القبول والتسجيل في جامعة الخليل:\n"
        return header + _format_admissions(data)
    except requests.ConnectionError:
        logger.warning("Mock API server is not running (admissions)")
        return "عذراً، تعذر الاتصال بخادم بيانات القبول والتسجيل. يرجى التأكد من تشغيل الخادم."
    except requests.HTTPError as exc:
        logger.warning("Admissions API HTTP error: %s", exc)
        return "عذراً، حدث خطأ أثناء جلب بيانات القبول."
    except Exception as exc:
        logger.error("Unexpected admissions tool error: %s", exc)
        return "عذراً، حدث خطأ غير متوقع أثناء جلب بيانات القبول."
