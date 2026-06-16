"""
Official Hebron University API connectors.

These connectors are designed to call real REST/JSON endpoints that the
university will provide. Until credentials and URLs are supplied, they
return an explicit "not configured" result — they NEVER inject fake data
into the production knowledge base.

When real API access is granted:
  1. Set endpoint_url on the DynamicSource row via Admin → Dynamic Sources.
  2. Set auth_token in one of the following formats:
       a) A raw JWT/API-key:  paste the token directly — sent as "Bearer <token>".
       b) A credential pair:  "username:password" — the connector will call
          <auth_base_url>/auth/token to obtain a JWT automatically.
          Set auth_base_url in the source_config (or let it default to
          the scheme+host of endpoint_url).
  3. Click "Sync now" — the connector will start fetching real data.

Expected API contracts (to be confirmed with the university IT team):
  Calendar      : GET <endpoint_url>  → JSON list of {id, title, start_date, end_date, description}
  Announcements : GET <endpoint_url>  → JSON list of {id, title, body, published_at, category}
  Admissions    : GET <endpoint_url>  → JSON list of {id, term, event, open_date, close_date, notes}
  Fees          : GET <endpoint_url>  → JSON list of {id, fee_type, amount_jod, currency, payment_timing, notes}
  Faculty       : GET <endpoint_url>?search=<term>  → JSON list of {id, name, name_en, title, college, department, role, email, specialization, office_hours}

Mock server (for testing):
  Run `python mock_api_server.py` (port 5001).
  Use auth_token = "hebron_api:test1234" and endpoint_url pointing to
  http://localhost:5001/api/<endpoint>.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from .base import BaseConnector, ConnectorResult, hash_content

logger = logging.getLogger(__name__)

# Network timeout for official API calls
_TIMEOUT_SEC = 30

# In-process JWT cache keyed by (auth_base_url, username) so we don't
# re-authenticate on every sync when credentials are valid.
_token_cache: Dict[tuple, str] = {}


def _resolve_base_url(endpoint_url: str) -> str:
    """Return scheme+host from a full endpoint URL, e.g. 'http://localhost:5001'."""
    parsed = urlparse(endpoint_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _obtain_jwt(auth_base_url: str, username: str, password: str) -> str:
    """
    POST to <auth_base_url>/auth/token with username/password credentials
    and return the access token string.  Caches the token in-process.

    Raises requests.HTTPError on auth failure (401 etc.).
    """
    cache_key = (auth_base_url, username)
    cached = _token_cache.get(cache_key)
    if cached:
        return cached

    url = f"{auth_base_url.rstrip('/')}/auth/token"
    resp = requests.post(
        url,
        json={"username": username, "password": password},
        timeout=_TIMEOUT_SEC,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token", "")
    if not token:
        raise ValueError("Auth response did not contain 'access_token'")
    _token_cache[cache_key] = token
    logger.debug("Obtained JWT for %s @ %s", username, auth_base_url)
    return token


def _invalidate_cache(auth_base_url: str, username: str) -> None:
    _token_cache.pop((auth_base_url, username), None)


class _OfficialApiConnector(BaseConnector):
    """
    Shared behaviour for all official-API connectors:
      - Resolves a Bearer token (raw JWT or username:password credential pair).
      - GET request with Authorization: Bearer header.
      - Expects a JSON array (list) response.
      - Validates that the list is non-empty.

    auth_token field semantics
    --------------------------
    • Empty / None          → no Authorization header (open endpoint).
    • Contains ":"          → treated as "username:password"; the connector
                              POSTs to /auth/token to get a JWT automatically.
    • No ":"                → used verbatim as a Bearer token.

    Optional source_config keys
    ---------------------------
    • auth_base_url  – override the base URL used for /auth/token.
                       Defaults to scheme+host extracted from endpoint_url.
    """

    def _get_bearer_token(self) -> Optional[str]:
        """
        Return the Bearer token string to use for this request,
        or None if the endpoint requires no authentication.
        """
        if not self.auth_token:
            return None

        # Credential-pair mode: "username:password"
        if ":" in self.auth_token:
            username, _, password = self.auth_token.partition(":")
            auth_base_url = (
                self.source_config.get("auth_base_url")
                or _resolve_base_url(self.endpoint_url)
            )
            try:
                return _obtain_jwt(auth_base_url, username, password)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 401:
                    # Token may have expired in cache — purge and retry once
                    _invalidate_cache(auth_base_url, username)
                    return _obtain_jwt(auth_base_url, username, password)
                raise

        # Raw-token mode
        return self.auth_token

    def fetch(self) -> Any:
        headers: Dict[str, str] = {"Accept": "application/json"}
        token = self._get_bearer_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        resp = requests.get(self.endpoint_url, headers=headers, timeout=_TIMEOUT_SEC)

        # If the token was cached and is now rejected (e.g. server restart),
        # purge cache and try once more with fresh credentials.
        if resp.status_code == 401 and self.auth_token and ":" in self.auth_token:
            username, _, _ = self.auth_token.partition(":")
            auth_base_url = (
                self.source_config.get("auth_base_url")
                or _resolve_base_url(self.endpoint_url)
            )
            _invalidate_cache(auth_base_url, username)
            token = self._get_bearer_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = requests.get(self.endpoint_url, headers=headers, timeout=_TIMEOUT_SEC)

        resp.raise_for_status()
        return resp.json()

    def validate(self, raw: Any) -> bool:
        return isinstance(raw, list) and len(raw) > 0


class CalendarConnector(_OfficialApiConnector):
    """
    Fetches university academic calendar events.

    Expected item keys: id, title, start_date, end_date, description
    Graceful fallback for missing optional keys.
    """

    def normalize(self, raw: Any) -> List[Dict[str, Any]]:
        records = []
        for item in raw:
            rid = str(item.get("id") or item.get("event_id") or "")
            title = (item.get("title") or item.get("name") or "").strip()
            description = (item.get("description") or item.get("details") or "").strip()
            start = (item.get("start_date") or item.get("start") or "").strip()
            end = (item.get("end_date") or item.get("end") or "").strip()

            content_parts = [f"University Calendar Event: {title}"]
            if start:
                content_parts.append(f"Start: {start}")
            if end:
                content_parts.append(f"End: {end}")
            if description:
                content_parts.append(f"Details: {description}")
            content = "\n".join(content_parts)

            if not rid or not title:
                logger.debug("CalendarConnector: skipping item with missing id/title: %s", item)
                continue

            records.append({
                "record_id": f"calendar_{rid}",
                "content": content,
                "effective_from": start or None,
                "effective_to": end or None,
                "version_hash": hash_content(content),
            })
        return records


class AnnouncementsConnector(_OfficialApiConnector):
    """
    Fetches university announcements / news.

    Expected item keys: id, title, body, published_at, category
    """

    def normalize(self, raw: Any) -> List[Dict[str, Any]]:
        records = []
        for item in raw:
            rid = str(item.get("id") or item.get("announcement_id") or "")
            title = (item.get("title") or "").strip()
            body = (item.get("body") or item.get("content") or item.get("text") or "").strip()
            published = (item.get("published_at") or item.get("date") or "").strip()
            category = (item.get("category") or "general").strip()

            content_parts = [f"University Announcement ({category}): {title}"]
            if published:
                content_parts.append(f"Published: {published}")
            if body:
                content_parts.append(body)
            content = "\n".join(content_parts)

            if not rid or not title:
                logger.debug("AnnouncementsConnector: skipping item with missing id/title: %s", item)
                continue

            records.append({
                "record_id": f"announcement_{rid}",
                "content": content,
                "effective_from": published or None,
                "effective_to": None,
                "version_hash": hash_content(content),
            })
        return records


class AdmissionsConnector(_OfficialApiConnector):
    """
    Fetches admission / registration deadlines.

    Expected item keys: id, term, event, open_date, close_date, notes
    """

    def normalize(self, raw: Any) -> List[Dict[str, Any]]:
        records = []
        for item in raw:
            rid = str(item.get("id") or item.get("admission_id") or "")
            term = (item.get("term") or item.get("semester") or "").strip()
            event = (item.get("event") or item.get("title") or "").strip()
            open_date = (item.get("open_date") or item.get("start") or "").strip()
            close_date = (item.get("close_date") or item.get("deadline") or item.get("end") or "").strip()
            notes = (item.get("notes") or item.get("description") or "").strip()

            content_parts = [f"Admissions & Registration: {event}"]
            if term:
                content_parts.append(f"Term/Semester: {term}")
            if open_date:
                content_parts.append(f"Opens: {open_date}")
            if close_date:
                content_parts.append(f"Closes/Deadline: {close_date}")
            if notes:
                content_parts.append(f"Notes: {notes}")
            content = "\n".join(content_parts)

            if not rid or not event:
                logger.debug("AdmissionsConnector: skipping item with missing id/event: %s", item)
                continue

            records.append({
                "record_id": f"admission_{rid}",
                "content": content,
                "effective_from": open_date or None,
                "effective_to": close_date or None,
                "version_hash": hash_content(content),
            })
        return records


class FeesConnector(_OfficialApiConnector):
    """
    Fetches the university fee schedule.

    Expected item keys: id, fee_type, fee_type_en, amount_jod, currency,
                        payment_timing, notes
    """

    def normalize(self, raw: Any) -> List[Dict[str, Any]]:
        records = []
        for item in raw:
            rid = str(item.get("id") or item.get("fee_id") or "")
            fee_type = (item.get("fee_type") or item.get("name") or "").strip()
            fee_type_en = (item.get("fee_type_en") or "").strip()
            amount = item.get("amount_jod") or item.get("amount") or ""
            currency = (item.get("currency") or "JOD").strip()
            timing = (item.get("payment_timing") or item.get("timing") or "").strip()
            notes = (item.get("notes") or item.get("description") or "").strip()

            content_parts = [f"University Fee: {fee_type}"]
            if fee_type_en:
                content_parts.append(f"({fee_type_en})")
            if amount:
                content_parts.append(f"المبلغ / Amount: {amount} {currency}")
            if timing:
                content_parts.append(f"توقيت الدفع / Payment timing: {timing}")
            if notes:
                content_parts.append(f"ملاحظات / Notes: {notes}")
            content = "\n".join(content_parts)

            if not rid or not fee_type:
                logger.debug("FeesConnector: skipping item with missing id/fee_type: %s", item)
                continue

            records.append({
                "record_id": f"fee_{rid}",
                "content": content,
                "effective_from": None,
                "effective_to": None,
                "version_hash": hash_content(content),
            })
        return records


class FacultyConnector(_OfficialApiConnector):
    """
    Fetches university faculty/staff directory.

    Syncs the full directory (no search param at sync time — we want all
    members indexed in Chroma for static retrieval).
    Expected item keys: id, name, name_en, title, college, department,
                        role, email, specialization, office_hours
    """

    def normalize(self, raw: Any) -> List[Dict[str, Any]]:
        records = []
        for item in raw:
            rid = str(item.get("id") or item.get("faculty_id") or "")
            name = (item.get("name") or "").strip()
            name_en = (item.get("name_en") or "").strip()
            title = (item.get("title") or "").strip()
            college = (item.get("college") or "").strip()
            department = (item.get("department") or "").strip()
            role = (item.get("role") or "").strip()
            email = (item.get("email") or "").strip()
            specialization = (item.get("specialization") or "").strip()
            office_hours = (item.get("office_hours") or "").strip()

            content_parts = [f"عضو هيئة تدريس / Faculty Member: {name}"]
            if name_en:
                content_parts.append(f"({name_en})")
            if title:
                content_parts.append(f"اللقب / Title: {title}")
            if college:
                content_parts.append(f"الكلية / College: {college}")
            if department:
                content_parts.append(f"القسم / Department: {department}")
            if role:
                content_parts.append(f"المنصب / Role: {role}")
            if specialization:
                content_parts.append(f"التخصص / Specialization: {specialization}")
            if email:
                content_parts.append(f"البريد الإلكتروني / Email: {email}")
            if office_hours:
                content_parts.append(f"ساعات المكتب / Office Hours: {office_hours}")
            content = "\n".join(content_parts)

            if not rid or not name:
                logger.debug("FacultyConnector: skipping item with missing id/name: %s", item)
                continue

            records.append({
                "record_id": f"faculty_{rid}",
                "content": content,
                "effective_from": None,
                "effective_to": None,
                "version_hash": hash_content(content),
            })
        return records


# Registry mapping source_type strings to connector classes
CONNECTOR_REGISTRY: Dict[str, type] = {
    "calendar": CalendarConnector,
    "announcements": AnnouncementsConnector,
    "admissions": AdmissionsConnector,
    "fees": FeesConnector,
    "faculty": FacultyConnector,
}


def get_connector(source_config: Dict[str, Any]) -> Optional[BaseConnector]:
    """
    Factory: return the right connector for the given source_config dict.
    Returns None if the source_type has no registered connector.
    """
    source_type = (source_config.get("source_type") or "").strip().lower()
    cls = CONNECTOR_REGISTRY.get(source_type)
    if cls is None:
        logger.warning("No connector registered for source_type=%r", source_type)
        return None
    return cls(source_config)
