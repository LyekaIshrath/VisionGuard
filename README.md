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


## Installing VisionGuard on Another Windows Laptop

Follow this guide to install and run VisionGuard on a new Windows 10/11 machine.

### Prerequisites

Required:
- **OS**: Windows 10 / 11 (64-bit)
- **Webcam**: Integrated laptop webcam or USB external camera
- **Python**: Python 3.13 (recommended: Python 3.13.x with py launcher)
- **Node.js / npm**: Node.js v20+ and npm v10+
- **Database**: MongoDB connection (local instance on mongodb://localhost:27017 or remote MongoDB Atlas connection string)

---

### Automated Setup (Recommended)

Run the included automated setup script in PowerShell:

`powershell
.\setup_windows.ps1
`

This script will:
1. Validate Python and Node.js/npm environments
2. Create ackend/.venv
3. Install backend dependencies from ackend/requirements.txt
4. Install frontend dependencies via 
pm ci
5. Verify MediaPipe Tasks models (pose_landmarker_lite.task, ace_landmarker.task)
6. Copy .env.example to .env if not already present

---

### Manual Installation

#### 1. Clone or Copy Project
`powershell
git clone <repo-url> visionguard
cd visionguard
`

#### 2. Backend Setup
`powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cd ..
`

#### 3. Frontend Setup
`powershell
cd frontend
npm ci
cd ..
`

#### 4. Environment Configuration
Copy the template configuration files:
`powershell
copy .env.example .env
copy backend\.env.example backend\.env
`

Edit .env and set:
- MONGODB_URI: Your MongoDB connection URI (e.g. mongodb://localhost:27017)
- MONGODB_DATABASE: Database name (e.g. isionguard)
- JWT_SECRET: A secure random secret key for token signing

#### 5. Verify MediaPipe Model Files
Ensure the pre-packaged task models exist in ackend/models/:
- ackend/models/pose_landmarker_lite.task
- ackend/models/face_landmarker.task

#### 6. Start VisionGuard
You can launch both services together using the startup script:
`powershell
.\start_visionguard.ps1
`

Or start them manually in two separate terminal windows:

**Terminal 1 (Backend):**
`powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
`

**Terminal 2 (Frontend):**
`powershell
cd frontend
npm run dev
`

Then open http://localhost:5173 in your browser.

---

### Optional: SMS & Push Notification Configuration

VisionGuard can send real-time SMS alerts (Twilio) and Web Push notifications. These are **optional**; if not configured, the system logs notifications locally without errors.

To enable SMS alerts via Twilio, add to .env:
`ini
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890
TWILIO_VERIFY_SERVICE_SID=optional_verify_service_sid
`

To enable Web Push notifications, add:
`ini
VAPID_PUBLIC_KEY=your_vapid_public_key
VAPID_PRIVATE_KEY=your_vapid_private_key
VAPID_SUBSCRIBER_EMAIL=admin@example.com
`
