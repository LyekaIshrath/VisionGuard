# VisionGuard — Deployment Guide

## Architecture Overview

VisionGuard is a **Hybrid Local-First** system with two distinct runtime boundaries:

### PWA UI (`PWA_INSTALLABLE = YES`)

The frontend is a Progressive Web App (PWA) that can be installed via Chrome or Edge.
It provides offline shell caching for static assets and an install-to-desktop experience.

### Local Companion (`LOCAL_RUNTIME_PACKAGING = NOT IMPLEMENTED`)

> **IMPORTANT**: The PWA UI does **not** install, start, update, or manage the Python/OpenCV/FastAPI local companion.
> Users must install and run the companion separately.

## System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 (21H1+) | Windows 11 |
| Browser | Chrome 114+, Edge 114+ | Chrome Latest |
| Python | 3.11+ | 3.13 |
| Camera | USB webcam | Integrated HD webcam |
| RAM | 4 GB | 8 GB |

## Local Companion Installation

```bash
# 1. Clone repository
git clone <repo-url>
cd visionguard/backend

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment (optional — Supabase cloud sync)
cp ../.env.example .env
# Edit .env with SUPABASE_URL, SUPABASE_ANON_KEY

# 4. Start the companion
python -m app.main
# Runs at http://127.0.0.1:8000
```

## Frontend Deployment

### Development

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

### Production Build

```bash
cd frontend
npm run build
# Serve dist/ with any static file server
# e.g.: npx serve dist/
```

## CORS Configuration

The companion's default CORS allowlist is:

```
http://localhost:5173
http://127.0.0.1:5173
http://localhost:4173
http://127.0.0.1:4173
http://localhost:8000
http://127.0.0.1:8000
```

Override via environment variable:

```bash
CORS_ALLOWED_ORIGINS='["http://localhost:5173"]' python -m app.main
```

## PWA Installation

1. Serve the frontend (dev or production build)
2. Navigate in Chrome/Edge
3. Click the **Install** button in the browser address bar
4. **The local companion must still be running separately**

## Security Headers

The companion sets the following headers on all non-WebSocket responses:

| Header | Value |
|---|---|
| `Content-Security-Policy` | Strict allowlist |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | camera=(), microphone=(), geolocation=() |
| `X-Request-ID` | Per-request UUID |

## Data Retention

Retention is enforced at three triggers:

1. **Authenticated app startup** — via `POST /api/v1/user/startup`
2. **Session finalization** — after each completed session
3. **Preference update** — when `data_retention_days` is changed

Retention only targets `status = 'COMPLETED'` sessions. `ACTIVE` and `INTERRUPTED` sessions are never deleted.
