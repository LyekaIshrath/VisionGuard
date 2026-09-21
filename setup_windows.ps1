# ====================================================================
# VisionGuard - Windows Automated Portability Setup Script
# Configures backend Python virtual environment and frontend dependencies
# ====================================================================

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "VisionGuard - Automated Environment Setup (Windows)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

# 1. Check Python installation
Write-Host ""
Write-Host "[1/8] Checking Python environment..." -ForegroundColor Yellow
$PythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyVer = & py -3.13 --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $PythonCmd = "py -3.13"
        Write-Host "  Found: $pyVer (using py -3.13 launcher)" -ForegroundColor Green
    } else {
        $pyVer = & py --version 2>&1
        $PythonCmd = "py"
        Write-Host "  Found: $pyVer (using py launcher)" -ForegroundColor Green
    }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyVer = & python --version 2>&1
    $PythonCmd = "python"
    Write-Host "  Found: $pyVer (using python command)" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Python is not installed or not in PATH! Please install Python 3.13." -ForegroundColor Red
    exit 1
}

# 2. Check Node & npm
Write-Host ""
Write-Host "[2/8] Checking Node.js and npm..." -ForegroundColor Yellow
if ((Get-Command node -ErrorAction SilentlyContinue) -and (Get-Command npm -ErrorAction SilentlyContinue)) {
    $nodeVer = & node -v
    $npmVer = & npm -v
    Write-Host "  Found Node: $nodeVer, npm: $npmVer" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Node.js / npm not found! Please install Node.js (LTS)." -ForegroundColor Red
    exit 1
}

# 3. Create Backend Virtual Environment
Write-Host ""
Write-Host "[3/8] Setting up backend virtual environment..." -ForegroundColor Yellow
$BackendDir = Join-Path $ProjectRoot "backend"
$VenvDir = Join-Path $BackendDir ".venv"

if (-not (Test-Path $VenvDir)) {
    Write-Host "  Creating virtual environment at $VenvDir..."
    if ($PythonCmd -eq "py -3.13") {
        & py -3.13 -m venv $VenvDir
    } else {
        & python -m venv $VenvDir
    }
} else {
    Write-Host "  Virtual environment already exists at $VenvDir" -ForegroundColor Green
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "  [ERROR] Virtual environment python executable not found at $VenvPython" -ForegroundColor Red
    exit 1
}

# 4. Install Backend Requirements
Write-Host ""
Write-Host "[4/8] Installing backend dependencies from requirements.txt..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip --quiet
$ReqFile = Join-Path $BackendDir "requirements.txt"
if (Test-Path $ReqFile) {
    & $VenvPip install -r $ReqFile
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Backend requirements installed successfully." -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] Failed to install backend requirements!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  [ERROR] requirements.txt not found at $ReqFile" -ForegroundColor Red
    exit 1
}

# 5. Install Frontend Dependencies
Write-Host ""
Write-Host "[5/8] Installing frontend dependencies via npm ci..." -ForegroundColor Yellow
$FrontendDir = Join-Path $ProjectRoot "frontend"
Push-Location $FrontendDir
try {
    & npm ci
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Frontend packages installed cleanly." -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] npm ci failed!" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

# 6. Verify MediaPipe Model Files
Write-Host ""
Write-Host "[6/8] Verifying MediaPipe Tasks models..." -ForegroundColor Yellow
$ModelsDir = Join-Path $BackendDir "models"
$PoseModel = Join-Path $ModelsDir "pose_landmarker_lite.task"
$FaceModel = Join-Path $ModelsDir "face_landmarker.task"

$modelsOk = $true
if (Test-Path $PoseModel) {
    $poseSize = (Get-Item $PoseModel).Length
    Write-Host "  [PASS] Pose model: $PoseModel ($poseSize bytes)" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Missing: $PoseModel" -ForegroundColor Red
    $modelsOk = $false
}

if (Test-Path $FaceModel) {
    $faceSize = (Get-Item $FaceModel).Length
    Write-Host "  [PASS] Face model: $FaceModel ($faceSize bytes)" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Missing: $FaceModel" -ForegroundColor Red
    $modelsOk = $false
}

if (-not $modelsOk) {
    Write-Host "  [WARNING] MediaPipe models missing. Pose/face perception will fail at runtime!" -ForegroundColor Yellow
}

# 7. Environment Configuration (.env) Check
Write-Host ""
Write-Host "[7/8] Checking environment configuration..." -ForegroundColor Yellow
$RootEnv = Join-Path $ProjectRoot ".env"
$BackendEnv = Join-Path $BackendDir ".env"

if (-not (Test-Path $RootEnv)) {
    Write-Host "  Copying .env.example -> .env (Root)..."
    Copy-Item (Join-Path $ProjectRoot ".env.example") $RootEnv
}
if (-not (Test-Path $BackendEnv)) {
    Write-Host "  Copying backend/.env.example -> backend/.env..."
    Copy-Item (Join-Path $BackendDir ".env.example") $BackendEnv
}

Write-Host "  [IMPORTANT] MongoDB configuration is required:" -ForegroundColor Magenta
Write-Host "  1. Ensure MongoDB service is running (locally on mongodb://localhost:27017 or remote URI)." -ForegroundColor Magenta
Write-Host "  2. Ensure JWT_SECRET is set to a secure string in .env." -ForegroundColor Magenta

# 8. Summary & Next Steps
Write-Host ""
Write-Host "[8/8] Setup Complete!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS TO START VISIONGUARD:" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option A: Use startup script:" -ForegroundColor Yellow
Write-Host "  .\start_visionguard.ps1"
Write-Host ""
Write-Host "Option B: Manual start:" -ForegroundColor Yellow
Write-Host "  Terminal 1 (Backend):"
Write-Host "    cd backend"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "  Terminal 2 (Frontend):"
Write-Host "    cd frontend"
Write-Host "    npm run dev"
Write-Host "==================================================" -ForegroundColor Cyan
