# SARMAAN II Coverage Dashboard — local dev server
# Usage: .\start_server.ps1
# Stop with Ctrl+C

$ErrorActionPreference = "Stop"
$port = 8080

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  SARMAAN II Coverage Dashboard" -ForegroundColor Green
Write-Host "  http://127.0.0.1:$port" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""

# Try local venv first, fall back to system python
$python = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
& $python -m uvicorn main:app --reload --port $port
