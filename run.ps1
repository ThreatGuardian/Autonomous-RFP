# One-command start for Windows PowerShell: installs dependencies, builds the web app
# and serves everything on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\Activate.ps1
python -m pip install --quiet --upgrade pip
pip install --quiet -r backend\requirements.txt

if (-not (Test-Path "frontend\node_modules")) { Push-Location frontend; npm install --silent; Pop-Location }
Push-Location frontend; npm run build --silent; Pop-Location

Set-Location backend
Write-Host "Tenderdesk is starting on http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
