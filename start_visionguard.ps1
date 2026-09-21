# ====================================================================
# VisionGuard - Windows Quick-Start Launcher
# Starts FastAPI backend and Vite frontend development server
# ====================================================================

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "VisionGuard - Starting Application..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$ProjectRoot = $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"

$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $VenvPython = "py -3.13"
    } else {
        $VenvPython = "python"
    }
}

Write-Host "1. Launching Backend Server on http://127.0.0.1:8000..." -ForegroundColor Green
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", "cd '$BackendDir'; & $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

Start-Sleep -Seconds 2

Write-Host "2. Launching Frontend Server on http://localhost:5173..." -ForegroundColor Green
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", "cd '$FrontendDir'; npm run dev"

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "VisionGuard started! Opening browser at http://localhost:5173..." -ForegroundColor Cyan
Start-Process "http://localhost:5173"
