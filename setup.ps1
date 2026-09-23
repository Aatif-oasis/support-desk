# Oasis Chatbot — one-command setup for Windows.
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1
#
# Creates the virtualenv, installs both stacks, sets up .env files,
# runs migrations and loads demo data. Safe to re-run.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }

Step "Checking prerequisites"

foreach ($cmd in @("python", "npm")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "$cmd not found. Install it first, then re-run this script."
    }
    Ok "$cmd found"
}

# Postgres and Redis are external services; warn rather than fail, because
# they may be running in Docker, in WSL, or on another machine entirely.
$pg = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
if ($pg -and $pg.Status -eq "Running") { Ok "PostgreSQL service running" }
else { Warn "PostgreSQL service not detected — make sure a database is reachable" }

$redis = Get-Service -Name "Memurai","redis*" -ErrorAction SilentlyContinue
if ($redis -and ($redis | Where-Object { $_.Status -eq "Running" })) { Ok "Redis (Memurai) running" }
else { Warn "Redis not detected — real-time chat will not work without it" }

Step "Setting up environment files"

$backendEnv = Join-Path $root "backend\.env"
if (Test-Path $backendEnv) {
    Ok ".env already exists (leaving it alone)"
} else {
    Copy-Item (Join-Path $root "backend\.env.example") $backendEnv
    # A random JWT secret per install — nobody should ship the placeholder.
    $secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
    (Get-Content $backendEnv) -replace "CHANGE_ME_TO_A_LONG_RANDOM_STRING", $secret | Set-Content $backendEnv
    Ok "Created backend\.env with a generated JWT secret"
    Warn "Now open backend\.env and set your real database password in DATABASE_URL"
}

$dashEnv = Join-Path $root "dashboard\.env.local"
if (-not (Test-Path $dashEnv)) {
    Copy-Item (Join-Path $root "dashboard\.env.local.example") $dashEnv
    Ok "Created dashboard\.env.local"
}

Step "Installing backend dependencies"

Set-Location (Join-Path $root "backend")
if (-not (Test-Path "venv")) {
    python -m venv venv
    Ok "Created virtualenv"
}
& ".\venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".\venv\Scripts\pip.exe" install --quiet -r requirements.txt
Ok "Python packages installed"

Step "Preparing the database"

& ".\venv\Scripts\alembic.exe" upgrade head
Ok "Tables created"

& ".\venv\Scripts\python.exe" -m app.seed
& ".\venv\Scripts\python.exe" -m app.seed_demo

Step "Installing dashboard dependencies"

Set-Location (Join-Path $root "dashboard")
npm install --silent
Ok "Node packages installed"

Set-Location $root

Write-Host @"

Setup complete.

Start the backend (terminal 1):
    cd backend
    .\venv\Scripts\activate
    uvicorn app.main:app --reload

Start the dashboard (terminal 2):
    cd dashboard
    npm run dev

Then open http://localhost:3000/login
    admin@demo.com / DemoPass123

Widget demo: open widget\demo.html in a browser.

"@ -ForegroundColor Green
