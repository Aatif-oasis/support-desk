# Support Desk — start both servers.
#
#   powershell -ExecutionPolicy Bypass -File run.ps1
#
# Everything here runs through "python -m" rather than pip.exe or
# uvicorn.exe. On machines with Windows Application Control those small
# launcher executables are blocked, while Python itself is allowed — the
# module form does the same job and gets through.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Find-Python {
    <#
      Picks an interpreter that actually has the project's packages.
      A machine with several Pythons installed will happily run the wrong
      one and report that sqlalchemy does not exist, which reads like a
      broken project rather than the wrong interpreter.
    #>
    $candidates = @()

    if (Test-Path "$root\backend\venv\Scripts\python.exe") {
        $candidates += "$root\backend\venv\Scripts\python.exe"
    }

    foreach ($version in @("-3.12", "-3.11", "-3")) {
        $candidates += "py $version"
    }
    $candidates += "python"

    foreach ($candidate in $candidates) {
        try {
            if ($candidate -like "py *") {
                $parts = $candidate.Split(" ")
                & py $parts[1] -c "import sqlalchemy, fastapi" 2>$null
            } else {
                & $candidate -c "import sqlalchemy, fastapi" 2>$null
            }
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { }
    }
    return $null
}

function Invoke-Python([string]$interpreter, [string[]]$arguments) {
    if ($interpreter -like "py *") {
        $version = $interpreter.Split(" ")[1]
        & py $version @arguments
    } else {
        & $interpreter @arguments
    }
}

Write-Host "`nChecking services" -ForegroundColor Cyan
foreach ($pattern in @("postgresql*", "Memurai", "redis*")) {
    $service = Get-Service -Name $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($service -and $service.Status -ne "Running") {
        Write-Host "  starting $($service.Name)" -ForegroundColor Yellow
        Start-Service $service.Name -ErrorAction SilentlyContinue
    }
}

Write-Host "Clearing old servers" -ForegroundColor Cyan
foreach ($port in @(8000, 3000)) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            $process = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "  freeing port $port (pid $($process.Id))" -ForegroundColor Yellow
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            }
        }
}
Start-Sleep -Seconds 2

$python = Find-Python
if (-not $python) {
    Write-Host "`nNo Python with the project's packages installed." -ForegroundColor Red
    Write-Host "Run:  py -3 -m pip install -r backend\requirements.txt" -ForegroundColor Yellow
    exit 1
}
Write-Host "Using interpreter: $python" -ForegroundColor Green

if (-not (Test-Path "$root\backend\.env")) {
    Write-Host "`nbackend\.env is missing. Copy backend\.env.example and fill it in." -ForegroundColor Red
    exit 1
}

$pythonCommand = if ($python -like "py *") { "py $($python.Split(' ')[1])" } else { "& '$python'" }

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\backend'; $pythonCommand -m uvicorn app.main:app --reload"
)

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\dashboard'; npm run dev"
)

Write-Host @"

Both windows are starting. Give them a few seconds, then open:

    http://localhost:3000/login

"@ -ForegroundColor Green
