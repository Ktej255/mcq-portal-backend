# Frontend ↔ Backend Integration Guide

How the **mcq-portal-frontend** (Next.js) and **mcq-portal-backend** (FastAPI)
connect. This document is descriptive only — it adds no behavior.

## Services at a glance

| | Repo | Stack |
|---|---|---|
| Frontend | `Ktej255/mcq-portal-frontend` | Next.js 16, React 19, Tailwind 4 |
| Backend | `Ktej255/mcq-portal-backend` | FastAPI 2.0.0, SQLAlchemy, PostgreSQL |

- **Service name:** MCQ Intelligence Portal API (`version 2.0.0`)
- **API base path:** `/api/v1`
- **Auth:** Firebase (`firebase-admin` on the backend)
- **AI:** Google Generative AI (Gemini)

## API surface

Health / status:

- `GET /` — service status JSON
- `GET /health` — health check

Routers (all under `/api/v1`):

| Router | Prefix |
|---|---|
| auth | `/api/v1/auth` |
| admin | `/api/v1/admin` |
| tests | `/api/v1/tests` |
| reports | `/api/v1/reports` |
| dashboard | `/api/v1/dashboard` |
| revision | `/api/v1/revision` |
| attempts | `/api/v1/attempts` |
| simulation | `/api/v1/simulation` |
| mains-upload | `/api/v1/mains-upload` |

## How the frontend points at the backend

The frontend reads the API base URL from `src/env.ts`:

```
NEXT_PUBLIC_API_BASE_URL
  -> falls back to NEXT_PUBLIC_API_URL
  -> defaults to "http://localhost:8000/api/v1"
```

To target a deployed backend, set `NEXT_PUBLIC_API_BASE_URL` to
`https://<your-backend-host>/api/v1` in the frontend environment.

Auth-related frontend env (see `src/env.ts`):

- `NEXT_PUBLIC_AUTH_PROVIDER`
- `NEXT_PUBLIC_USE_MOCK_AUTH` (defaults to mock in local dev)
- `NEXT_PUBLIC_DEBUG_API`, `NEXT_PUBLIC_ENABLE_LEGACY_API`

## CORS

CORS is configured in `app/main.py` from `settings.BACKEND_CORS_ORIGINS`
(`app/core/config.py`). The defaults already allow local dev and the Vercel
frontend:

```
http://localhost:3000
http://localhost:3001
http://127.0.0.1:3000
http://127.0.0.1:3001
http://localhost:8000
http://127.0.0.1:8000
https://mcq-portal-frontend-yo5i.vercel.app
https://mcq-portal-frontend.vercel.app
```

Override with the `BACKEND_CORS_ORIGINS` env var (comma-separated, JSON list,
or `*`). Provided values are merged with the defaults.

## Backend environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgres://` is auto-upgraded to `postgresql://`) | `postgresql://postgres:password@localhost:5432/mcq_portal` |
| `BACKEND_CORS_ORIGINS` | Allowed origins (merged with defaults) | see CORS defaults above |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Firebase/GCP service-account JSON | _unset_ |
| `FIREBASE_PROJECT_ID` | Firebase project id | `mcq-intelligence-portal` |
| `GOOGLE_API_KEY` | Google Generative AI (Gemini) key | _unset_ |
| `ADMIN_EMAILS` | Bootstrap admin email(s) | _configured in `config.py`_ |
| `SCHEMA_CHECK_STRICT` | Strict schema checks | `false` |

> Never commit real secrets. Use a local `.env` (it is git-ignored) or your
> deployment platform's secret manager.

## Local development (reference)

Backend (PostgreSQL must be running and `DATABASE_URL` set):

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend (point it at the backend):

```bash
# .env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

```bash
npm install
npm run dev
```

Interactive API docs are available at `http://localhost:8000/docs` once the
backend is running.

## Request flow (summary)

```
Browser (Next.js)
  -> Firebase auth (ID token)
  -> fetch NEXT_PUBLIC_API_BASE_URL + /<router>/...
       Authorization: Bearer <Firebase ID token>
  -> FastAPI verifies token (firebase-admin) -> SQLAlchemy / PostgreSQL
```
