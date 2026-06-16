# Hebron University RAG Chatbot

An Arabic-first Retrieval-Augmented Generation (RAG) chatbot for Hebron University students and staff, featuring a React admin panel, embeddable widget, multi-channel messaging integrations, and a live-data ingestion pipeline.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Setup](#setup)
3. [Running the Applications](#running-the-applications)
4. [Mock API Server](#mock-api-server)
5. [Configuring Dynamic Sources](#configuring-dynamic-sources)
6. [Embeddable Widget](#embeddable-widget)
7. [Admin Panel](#admin-panel)
8. [API Reference](#api-reference)
9. [Rate Limiting](#rate-limiting)
10. [Project Structure](#project-structure)
11. [Security Notes](#security-notes)

---

## Requirements

| Tool       | Version                  |
| ---------- | ------------------------ |
| Python     | 3.10+                    |
| PostgreSQL | 14+                      |
| Ollama     | latest                   |
| Node.js    | 18+ _(admin panel only)_ |

> **Note:** A conda environment is recommended but any Python virtualenv works.

---

## Setup

### 1. Create and activate a Python environment

```bash
conda create -n arabic-rag python=3.10 -y
conda activate arabic-rag
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
# Copy the template (located in scripts/)
cp scripts/.env.example .env
# Edit .env with your PostgreSQL credentials, Ollama settings, and secrets
```

Key variables to set in `.env`:

| Variable             | Description                                          |
| -------------------- | ---------------------------------------------------- |
| `DATABASE_URL`       | PostgreSQL connection string — **required**          |
| `LLM_MODEL`          | Ollama model name (e.g. `llama3`)                    |
| `EMBED_MODEL`        | Ollama embedding model                               |
| `OLLAMA_BASE_URL`    | Ollama server URL (default `http://localhost:11434`) |
| `LLM_PROVIDER`       | `ollama` (default) or `openai_compatible`            |
| `LLM_API_KEY`        | API key for OpenAI-compatible providers              |
| `LLM_API_BASE_URL`   | Base URL for OpenAI-compatible providers             |
| `JWT_SECRET_KEY`     | Secret for signing admin JWTs                        |
| `RAG_API_HOST`       | Flask bind host (default `0.0.0.0`)                  |
| `RAG_API_PORT`       | Flask bind port (default `5000`)                     |
| `TELEGRAM_BOT_TOKEN` | Telegram webhook integration                         |
| `WHATSAPP_*`         | WhatsApp Cloud API credentials                       |
| `MESSENGER_*`        | Facebook Messenger credentials                       |

### 4. Database initialisation

The database schema is created **automatically** when the main application starts (`rag_api.py` imports `database.py` which calls `init_db()`). No separate migration step is required.

On first run, a default admin account is seeded:

| Field    | Value        |
| -------- | ------------ |
| Username | `ChatBot`    |
| Password | `Hebron@uni` |

> **Change these credentials immediately in any non-local environment.**

### 5. Install admin panel dependencies _(optional)_

```bash
cd admin-panel
npm install
cd ..
```

---

## Running the Applications

### Main chatbot API (port 5000)

```bash
conda activate arabic-rag
python rag_api.py
```

This starts the Flask server (via Waitress if installed, otherwise Flask's built-in server). All admin API routes, webhook endpoints, and the widget are served from this single process.

### Admin panel — development mode (port 5173)

```bash
cd admin-panel
npm run dev
```

Vite proxies `/api`, `/admin/*`, `/files`, `/widget`, and other backend routes to `localhost:5000`.

### Admin panel — production build

```bash
cd admin-panel
npm run build
```

The built files are served by Flask at **`http://localhost:5000/admin-panel/`** — no separate Node process needed in production.

### Mock university API — optional (port 5001)

```bash
python mock_api_server.py
```

---

## Mock API Server

`mock_api_server.py` simulates the university's live REST API so the RAG connectors and tool routing can be developed and tested without real credentials.

### Endpoints

| Method | Endpoint             | Auth required | Description                           |
| ------ | -------------------- | ------------- | ------------------------------------- |
| POST   | `/auth/token`        | No            | Returns a JWT for valid credentials   |
| GET    | `/api/calendar`      | Bearer JWT    | Academic calendar events              |
| GET    | `/api/announcements` | Bearer JWT    | University announcements              |
| GET    | `/api/admissions`    | Bearer JWT    | Admissions / registration dates       |
| GET    | `/api/fees`          | Bearer JWT    | Fee information                       |
| GET    | `/api/faculty`       | Bearer JWT    | Faculty search (`?search=` supported) |
| GET    | `/health`            | No            | Health check                          |

### Mock credentials

```
username : hebron_api
password : test1234
```

### Quick smoke test (PowerShell)

```powershell
# 1. Get a token
$resp = Invoke-RestMethod -Uri http://localhost:5001/auth/token `
        -Method POST `
        -ContentType "application/json" `
        -Body '{"username":"hebron_api","password":"test1234"}'
$token = $resp.access_token

# 2. Fetch calendar data
Invoke-RestMethod -Uri http://localhost:5001/api/calendar `
    -Headers @{ Authorization = "Bearer $token" }
```

### Quick smoke test (bash)

```bash
TOKEN=$(curl -s -X POST http://localhost:5001/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"hebron_api","password":"test1234"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/calendar
```

---

## Configuring Dynamic Sources

Dynamic Sources are configured in the Admin panel under **Dynamic Sources**. Each source has three key fields:

| Field           | Description                                      |
| --------------- | ------------------------------------------------ |
| `endpoint_url`  | Full URL of the API endpoint to fetch            |
| `auth_token`    | Authentication credential (see modes below)      |
| `auth_base_url` | _(optional)_ Override base URL for `/auth/token` |

### `auth_token` field modes

**Mode A — Raw Bearer token / API key**

Paste the token directly; it is sent as `Authorization: Bearer <value>`.

```
auth_token : eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Mode B — Username:Password (auto JWT)**

Use `username:password` format. The connector calls `<auth_base_url>/auth/token` to obtain a JWT automatically. Tokens are cached; expired tokens trigger one re-authentication.

```
auth_token : hebron_api:test1234
```

### Pointing sources at the mock server

| Source        | `endpoint_url`                            | `auth_token`          |
| ------------- | ----------------------------------------- | --------------------- |
| Calendar      | `http://localhost:5001/api/calendar`      | `hebron_api:test1234` |
| Announcements | `http://localhost:5001/api/announcements` | `hebron_api:test1234` |
| Admissions    | `http://localhost:5001/api/admissions`    | `hebron_api:test1234` |
| Fees          | `http://localhost:5001/api/fees`          | `hebron_api:test1234` |
| Faculty       | `http://localhost:5001/api/faculty`       | `hebron_api:test1234` |

After saving, click **Sync Now**. The connector will authenticate, fetch the data, and embed it into ChromaDB under a `dynamic_*` namespace.

### Switching to the real university API

1. Update `endpoint_url` to the production URL.
2. Set `auth_token` to the real credentials (raw token or `user:pass`).
3. Optionally set `auth_base_url` if the auth server differs.
4. Click **Sync Now**.

No code changes are required.

---

## Embeddable Widget

A lightweight chat widget (`widget/`) can be embedded into any web page. Flask serves it at `/widget/`. The embed snippet is in `scripts/widget-embed.txt` and looks like:

```html
<link rel="stylesheet" href="https://your-domain/widget/widget.css" />
<script src="https://your-domain/widget/widget.js"></script>
```

The `/widget/config` endpoint returns branding (base64 logo) and FAQ data used to initialise the widget.

---

## Admin Panel

The React admin panel (port 5173 in dev, `/admin-panel/` in prod) provides:

- **KPI Dashboard** — conversation volume, feedback scores, unanswered-query rate
- **Chat History** — browse and search all sessions and messages
- **File Manager** — upload, delete, and inspect document chunks; stale-document lifecycle workflow
- **Dynamic Sources** — configure REST endpoints, trigger syncs, view sync history and embedded chunks
- **FAQs** — create, edit, normalize, and delete FAQ pairs
- **Unanswered Queries** — review and resolve queries the bot could not answer
- **Overrides** — exact-match answer overrides that bypass RAG
- **AI Settings** — configure chatbot copy (name, greeting, etc.)
- **LLM Settings** — switch between Ollama and OpenAI-compatible providers, test connectivity

Login at `/admin-panel/` with the admin credentials.

---

## API Reference

All endpoints are on the main Flask server (default port **5000**).

### Chat & Sessions

| Method | Route                             | Description                                                |
| ------ | --------------------------------- | ---------------------------------------------------------- |
| POST   | `/chat`                           | Send a question; body: `{question, session_id?, user_id?}` |
| POST   | `/chat/faq`                       | Store an FAQ pair without invoking the LLM                 |
| POST   | `/chat/audio`                     | Multipart audio upload; supports `transcribe_only` flag    |
| GET    | `/users/<user_id>/sessions`       | List sessions for a user                                   |
| GET    | `/sessions/<session_id>/messages` | Messages in a session                                      |
| DELETE | `/sessions/<session_id>`          | Delete session, messages, and feedback                     |

### Feedback

| Method | Route       |
| ------ | ----------- |
| POST   | `/feedback` |

### Files & Ingestion

| Method | Route                        |
| ------ | ---------------------------- |
| POST   | `/load`                      |
| GET    | `/files`                     |
| GET    | `/files/<filename>/download` |
| GET    | `/files/<filename>/chunks`   |
| DELETE | `/files/<filename>`          |

### Health

| Method | Route     |
| ------ | --------- |
| GET    | `/health` |

### Webhooks

| Method    | Route                |
| --------- | -------------------- |
| POST      | `/webhook/telegram`  |
| GET, POST | `/webhook/whatsapp`  |
| GET, POST | `/webhook/messenger` |

### Admin API (JWT required — `Authorization: Bearer <token>`)

| Method      | Route                                           |
| ----------- | ----------------------------------------------- |
| POST        | `/api/admin/login`                              |
| GET         | `/api/admin/me`                                 |
| GET, POST   | `/api/admin/faqs`                               |
| POST        | `/api/admin/faqs/normalize`                     |
| PUT, DELETE | `/api/admin/faqs/<faq_id>`                      |
| GET, POST   | `/api/admin/overrides`                          |
| PUT, DELETE | `/api/admin/overrides/<override_id>`            |
| GET, PUT    | `/api/admin/settings`                           |
| POST        | `/api/admin/settings/restore`                   |
| GET         | `/api/admin/unanswered`                         |
| PUT         | `/api/admin/unanswered/<query_id>/resolve`      |
| POST        | `/api/admin/unanswered/resolve-all`             |
| GET         | `/api/admin/files/stale`                        |
| GET         | `/api/admin/files/<record_id>/versions`         |
| PUT         | `/api/admin/files/<record_id>/freshness`        |
| PUT         | `/api/admin/files/<record_id>/review`           |
| PUT         | `/api/admin/files/<record_id>/replace`          |
| POST        | `/api/admin/files/<record_id>/retire`           |
| POST        | `/api/admin/files/<record_id>/reindex`          |
| POST        | `/api/admin/files/<record_id>/restore`          |
| GET, POST   | `/api/admin/dynamic-sources`                    |
| PUT, DELETE | `/api/admin/dynamic-sources/<source_id>`        |
| POST        | `/api/admin/dynamic-sources/<source_id>/sync`   |
| GET         | `/api/admin/dynamic-sources/<source_id>/runs`   |
| GET         | `/api/admin/dynamic-sources/<source_id>/chunks` |
| GET, PUT    | `/api/admin/llm-config`                         |
| GET         | `/api/admin/llm-config/test`                    |
| GET         | `/api/admin/tool-routing/status`                |
| GET         | `/api/admin/scheduler/jobs`                     |

---

## Project Structure

```
hebron-chatbot/
├── rag_api.py                # Main Flask application (port 5000)
├── mock_api_server.py        # Mock university REST API (port 5001)
├── mock_university_api.json  # Static data served by the mock server
├── database.py               # SQLAlchemy models & DB init (auto-runs on import)
├── requirements.txt
├── .gitignore
│
├── src/
│   ├── rag_system.py         # Core Arabic RAG pipeline (ArabicRAGChatbot)
│   ├── dynamic_ingestion.py  # APScheduler jobs for syncing dynamic sources
│   ├── tools.py              # LangChain tools for live API tool-routing
│   ├── utils.py              # Arabic normalisation, audio transcription helpers
│   ├── rate_limits.py        # Redis-backed weighted rate limiting for LLM usage
│   └── connectors/
│       ├── __init__.py
│       ├── base.py           # Abstract connector + ConnectorResult
│       └── official_api.py   # Calendar / Announcements / Admissions / Fees / Faculty
│
├── widget/
│   ├── index.html            # Standalone widget test page
│   ├── widget.css
│   └── widget.js             # Embeddable chat widget
│
├── admin-panel/              # React 18 + TypeScript + Vite + Tailwind admin UI
│   ├── src/
│   │   ├── pages/            # DashboardLayout, LoginPage
│   │   ├── components/       # KPIDashboard, ChatHistory, FileManager, FAQManager, …
│   │   ├── api/              # Typed API clients (auth, files, analytics, faqs, …)
│   │   ├── contexts/         # AuthContext (JWT state)
│   │   └── hooks/            # useData
│   ├── package.json
│   └── vite.config.ts        # Dev proxy → localhost:5000
│
├── scripts/
│   ├── .env.example          # Environment variable template — copy to project root
│   ├── widget-embed.txt      # Embed snippet for the chat widget
│   ├── NgrokLink.txt         # Ngrok tunnel helper
│   ├── cleanup_ghost_chunks.py
│   ├── find_ghost_tables.py
│   ├── fix_pg_sequences.py
│   ├── fix_timezones.py
│   ├── migrate_data.py
│   └── reassign_sessions.py
│
├── assets/                   # Branding assets (logo, campus map images)
├── uploads/                  # Uploaded documents
└── chroma_db/                # ChromaDB vector store
```

---

## Rate Limiting

The chatbot uses Redis-backed weighted rate limiting to protect the expensive RAG/LLM pipeline. FAQ answers and manual override answers are **always free** and never consume quota.

### How it works

| Message type | Quota cost | Configurable via |
| -------------------- | ---------- | ------------------------------ |
| Short text → LLM | 1 | `RATE_LIMIT_TEXT_COST` |
| Long text → LLM | 2 | `RATE_LIMIT_LONG_TEXT_COST` |
| Audio → transcribe + LLM | 3 | `RATE_LIMIT_AUDIO_COST` |
| FAQ click | 0 | — |
| Manual override answer | 0 | — |

Limits are enforced **per user** (by `user_id`, `session_id`, or platform sender ID) with two independent windows:

- Per-minute: resets every 60 seconds.
- Per-day: resets at UTC midnight.

When either window is exhausted the API returns HTTP `429` (website) or sends a bilingual message to the user (Telegram/WhatsApp/Messenger) without calling the LLM.

### Setup

**1. Install and start Redis** (Windows — use Redis for Windows or Docker):

```powershell
# Using Docker (recommended)
docker run -d --name redis-rag -p 6379:6379 redis:7-alpine

# Or install Redis for Windows and run
redis-server
```

**2. Install the Python dependency** (inside the `arabic-rag` conda environment):

```bash
conda activate arabic-rag
pip install -r requirements.txt
```

`redis` is already listed in `requirements.txt`.

**3. Configure `.env`** (copy from `scripts/.env.example`):

```env
RATE_LIMIT_ENABLED=true
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_LLM_PER_MINUTE=10
RATE_LIMIT_LLM_PER_DAY=100
RATE_LIMIT_TEXT_COST=1
RATE_LIMIT_LONG_TEXT_CHARS=800
RATE_LIMIT_LONG_TEXT_COST=2
RATE_LIMIT_AUDIO_COST=3
RATE_LIMIT_FAIL_OPEN=true
```

Set `RATE_LIMIT_ENABLED=false` to disable rate limiting completely (e.g. for local development without Redis).

Set `RATE_LIMIT_FAIL_OPEN=false` to block requests when Redis is unreachable (strict cost control); the default `true` keeps the chatbot available and logs a warning.

### Manual smoke tests

Start the backend first:

```bash
conda activate arabic-rag
python rag_api.py
```

**Test 1 — FAQ is always served (not blocked by quota):**

```powershell
# This endpoint never consumes LLM quota
Invoke-RestMethod -Uri http://localhost:5000/chat/faq `
  -Method POST -ContentType "application/json" `
  -Body '{"faq_id":1,"question":"test","answer":"test answer","session_id":"smoke-test-1"}'
```

**Test 2 — Normal chat works until quota is exceeded:**

```powershell
# Send 12 messages quickly (default per-minute limit is 10)
1..12 | ForEach-Object {
  $r = Invoke-WebRequest -Uri http://localhost:5000/chat `
    -Method POST -ContentType "application/json" `
    -Body "{`"question`":`"what is hebron university`",`"user_id`":`"smoke-test-user`"}" `
    -SkipHttpErrorCheck
  Write-Host "Request $_ → $($r.StatusCode)"
}
# Requests 1-10 → 200, requests 11-12 → 429
```

**Test 3 — Manual override is always served after quota is exhausted:**

```powershell
# After the test above, override answers still work immediately
Invoke-RestMethod -Uri http://localhost:5000/chat `
  -Method POST -ContentType "application/json" `
  -Body '{"question":"مرحبا","user_id":"smoke-test-user"}'
# (Assuming "مرحبا" or similar is a configured trigger phrase)
```

**Test 4 — Rate-limited response shape:**

A `429` response from `/chat` contains:

```json
{
  "answer": "عذراً، لقد تجاوزت الحد المسموح ...",
  "rate_limited": true,
  "retry_after_seconds": 47,
  "remaining_minute": 0,
  "remaining_day": 88
}
```

**Test 5 — Verify Redis is not required when disabled:**

```bash
# In .env: RATE_LIMIT_ENABLED=false  (no Redis running)
conda activate arabic-rag
python rag_api.py   # should start without errors
```

---

## Security Notes

- **Default admin credentials** (`ChatBot` / `Hebron@uni`) are seeded on first boot — **change them immediately** before any external access.
- **`JWT_SECRET_KEY`** and **`MOCK_JWT_SECRET`** must be strong random secrets in production.
- **LLM API keys** are stored in plain text in the database — encrypt them for production deployments.
- **`.env`** is gitignored; never commit it.
