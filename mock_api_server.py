"""
Mock REST API server for Hebron University — testing only.

Simulates the university's live API so the RAG connectors can be
developed and tested without real credentials.

Endpoints
---------
POST /auth/token
    Body : {"username": "hebron_api", "password": "test1234"}
    Returns : {"access_token": "<jwt>", "token_type": "bearer"}

GET /api/calendar        — requires Authorization: Bearer <token>
GET /api/announcements   — requires Authorization: Bearer <token>
GET /api/admissions      — requires Authorization: Bearer <token>
GET /api/fees            — requires Authorization: Bearer <token>
GET /api/faculty         — requires Authorization: Bearer <token>
                           Optional query param: ?search=<name|department|college>

Run
---
    conda activate arabic-rag
    python mock_api_server.py

The server starts on http://localhost:5001 (separate from the main
chatbot on port 5000).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path

import jwt
from flask import Flask, jsonify, request

# ── Configuration ──────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("MOCK_JWT_SECRET", "mock-secret-key-do-not-use-in-prod")
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 24

MOCK_CREDENTIALS = {
    "hebron_api": "test1234",
}

# Path to the mock data file (same directory as this script)
DATA_FILE = Path(__file__).with_name("mock_university_api.json")

app = Flask(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_data() -> dict:
    """Load and return the contents of mock_university_api.json."""
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def _create_token(username: str) -> str:
    """Return a signed JWT for the given username."""
    payload = {
        "sub": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    """Decode and verify a JWT.  Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def require_auth(f):
    """Decorator: enforce a valid Bearer token in the Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth_header[len("Bearer "):]
        try:
            _decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.PyJWTError as exc:
            return jsonify({"error": f"Invalid token: {exc}"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Auth endpoint ──────────────────────────────────────────────────────────────

@app.post("/auth/token")
def auth_token():
    """
    Authenticate and return a JWT.

    Request body (JSON):
        {"username": "hebron_api", "password": "test1234"}

    Response (200):
        {"access_token": "<jwt>", "token_type": "bearer"}
    """
    body = request.get_json(silent=True) or {}
    username = body.get("username", "")
    password = body.get("password", "")

    expected = MOCK_CREDENTIALS.get(username)
    if expected is None or expected != password:
        return jsonify({"error": "Invalid credentials"}), 401

    token = _create_token(username)
    return jsonify({"access_token": token, "token_type": "bearer"}), 200


# ── Protected data endpoints ───────────────────────────────────────────────────

@app.get("/api/calendar")
@require_auth
def api_calendar():
    """Return the list of academic calendar events."""
    data = _load_data()
    return jsonify(data.get("calendar", [])), 200


@app.get("/api/announcements")
@require_auth
def api_announcements():
    """Return the list of university announcements."""
    data = _load_data()
    return jsonify(data.get("announcements", [])), 200


@app.get("/api/admissions")
@require_auth
def api_admissions():
    """Return the list of admissions and registration deadlines."""
    data = _load_data()
    return jsonify(data.get("admissions", [])), 200


@app.get("/api/fees")
@require_auth
def api_fees():
    """Return the university fee schedule."""
    data = _load_data()
    return jsonify(data.get("fees", [])), 200


@app.get("/api/faculty")
@require_auth
def api_faculty():
    """
    Return faculty members, optionally filtered by a search term.
    The ?search= param matches against name (Arabic/English), department,
    college, role, and specialization — case-insensitive.
    """
    data = _load_data()
    faculty = data.get("faculty", [])
    search = request.args.get("search", "").strip().lower()
    if search:
        import re as _re
        # Split the search string into meaningful tokens (drop tiny words/punctuation).
        # This handles cases where the LLM passes the full question as the query,
        # e.g. "Dr. Khalil Massri's office hours" → tokens ["khalil", "massri", "office", "hours"].
        # A member matches if ANY of its name tokens appear in the search tokens,
        # OR if the full search string is a substring of the haystack (exact phrase match).
        tokens = [t for t in _re.split(r"[\s\.,'\-؟!،]+", search.lower()) if len(t) > 2]

        def _matches(member: dict) -> bool:
            haystack = " ".join([
                member.get("name", ""),
                member.get("name_en", ""),
                member.get("college", ""),
                member.get("college_en", ""),
                member.get("department", ""),
                member.get("department_en", ""),
                member.get("role", ""),
                member.get("specialization", ""),
            ]).lower()
            # Full phrase match
            if search in haystack:
                return True
            # Token match: any meaningful token from the query hits the haystack
            return any(tok in haystack for tok in tokens)

        faculty = [m for m in faculty if _matches(m)]
    return jsonify(faculty), 200


# ── Health check (no auth required) ───────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok", "server": "Hebron University Mock API"}), 200


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Hebron University Mock API Server")
    print("  http://localhost:5001")
    print()
    print("  POST /auth/token")
    print('       body: {"username":"hebron_api","password":"test1234"}')
    print()
    print("  GET  /api/calendar        (Bearer token required)")
    print("  GET  /api/announcements   (Bearer token required)")
    print("  GET  /api/admissions      (Bearer token required)")
    print("  GET  /api/fees            (Bearer token required)")
    print("  GET  /api/faculty         (Bearer token required, ?search= optional)")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=True)
