# VisionGuard

> **Human Safety & Wellness Intelligence** — Real-time posture and alertness monitoring, running entirely on your local machine.

[![CI](https://github.com/your-org/visionguard/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/visionguard/actions)

## Architecture

VisionGuard uses a **Hybrid Local-First** architecture:

| Component | Runtime | Description |
|---|---|---|
| **Local Companion** | Python 3.13 + FastAPI | OpenCV/MediaPipe inference, REST API, WebSocket |
| **PWA Frontend** | React + Vite | Installable SPA, served from `localhost:5173` or `dist/` |
| **Cloud** | Supabase (optional) | Persistent session aggregates only — no raw frames |

```
Browser/PWA
    |  WebSocket + REST
    v
Local Companion (FastAPI :8000)
    |  in-process
    v
OpenCV VideoCapture --> MediaPipe --> Analysis --> Alert Orchestrator
    |  aggregated metrics only
    v
Supabase (optional cloud)
```

## PWA Status

| Status | Detail |
|---|---|
| `PWA_INSTALLABLE` | **YES** — Install from Chrome/Edge browser menu |
| `LOCAL_RUNTIME_PACKAGING` | **NOT IMPLEMENTED** — must run `python -m app.main` separately |

## Quick Start

### Prerequisites

- **Windows 10/11** (primary target)
- Python 3.13+
- Node.js 20+
- Webcam (USB or integrated)
- Chrome 114+ or Edge 114+

### 1. Start the Local Companion

```bash
cd backend
pip install -r requirements.txt
python -m app.main
# Companion runs at http://127.0.0.1:8000
```

### 2. Start the Frontend (development)

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

### 3. Install as PWA

1. Navigate to `http://localhost:5173` in Chrome or Edge
2. Click the **Install** button in the address bar
3. VisionGuard is now installed as a desktop app
4. **Note:** The local companion must still be running separately

## Camera Privacy

- Camera is captured **exclusively by the Python local companion** via OpenCV
- The browser/PWA **never** calls `getUserMedia`
- Raw frames are **never stored or uploaded**
- Only aggregated wellness metrics are synced to cloud (if configured)

## Development

```bash
# Backend tests
cd backend && python -m pytest tests/ -v

# Frontend TypeScript check
cd frontend && npx tsc --noEmit

# Frontend production build
cd frontend && npm run build
```

## Version

Current version: see [VERSION](VERSION)

## See also

- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — Production deployment guide
