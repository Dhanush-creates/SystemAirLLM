# One-time setup. Uses the offline\ folder when it exists, the internet otherwise.
# Windows PowerShell 5.1 compatible.
param([switch]$SkipModels)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$offline = Join-Path $root "offline"

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "   [ok] $text" -ForegroundColor Green }
function Warn($text) { Write-Host "   [!]  $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "   [X]  $text" -ForegroundColor Red }

# ---- 0. Folder location ----
# Windows limits a file path to 260 characters unless long paths are enabled, and the Python
# environment adds about 130 characters below this folder.
if ($root.Length -gt 120) {
    $long = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -ErrorAction SilentlyContinue).LongPathsEnabled
    if ($long -ne 1) {
        Fail "This folder's path is $($root.Length) characters long, which is too long for Windows."
        Write-Host "        Move the folder to a short path such as C:\workbench and run setup again."
        exit 1
    }
}

# Models are stored on the system drive (in the user profile) and need a lot of room.
$drive = Get-PSDrive -Name $env:USERPROFILE.Substring(0, 1) -ErrorAction SilentlyContinue
if ($drive -and -not $SkipModels) {
    $freeGB = [math]::Round($drive.Free / 1GB)
    if ($freeGB -lt 50) { Warn "Only $freeGB GB free on drive $($drive.Name):. The models for a 12 GB GPU need about 45 GB." }
}

# ---- 1. Python ----
Step "Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Fail "Python not found. Install Python 3.10 or newer from python.org (tick 'Add python.exe to PATH'), then run setup again."; exit 1 }
$ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2]); sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Fail "Python $ver is too old. Install Python 3.10 or newer."; exit 1 }
Ok "Python $ver"

# ---- 2. Environment and packages ----
Step "Python environment (.venv)"
$py = Join-Path $root ".venv\Scripts\python.exe"
$venvOk = $false
if (Test-Path $py) { & $py -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $venvOk = $true } }
if (-not $venvOk) {
    # A .venv copied from another machine does not work; rebuild it.
    if (Test-Path (Join-Path $root ".venv")) { Remove-Item -Recurse -Force (Join-Path $root ".venv") }
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Could not create .venv"; exit 1 }
}
$wheels = Join-Path $offline "wheels"
if (Test-Path $wheels) {
    Write-Host "   installing packages from offline\wheels"
    & $py -m pip install -q --no-index --find-links $wheels -r requirements.txt
} else {
    Write-Host "   installing packages from the internet"
    & $py -m pip install -q --disable-pip-version-check -r requirements.txt
}
if ($LASTEXITCODE -ne 0) { Fail "Package install failed. For an offline install the wheels must match this Python version ($ver)."; exit 1 }
Ok "packages installed"

# ---- 3. Ollama (model server) ----
Step "Ollama model server"
function Find-Ollama {
    $c = Get-Command ollama -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $p = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $p) { return $p }
    return $null
}
$ollama = Find-Ollama
if (-not $ollama) {
    $installer = Join-Path $offline "OllamaSetup.exe"
    if (Test-Path $installer) {
        Write-Host "   installing from offline\OllamaSetup.exe"
        Start-Process $installer -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
    } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "   installing with winget"
        winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Null
    }
    $ollama = Find-Ollama
}
if ($ollama) {
    Ok "Ollama at $ollama"
    # The installer starts the Ollama desktop app, which contacts external addresses. The workbench
    # stops it and runs the server itself with cloud features off (model downloads still work).
    & $py -c "from workbench import modelserver; print('   ' + modelserver.ensure())"
    $up = $false
    try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 5 | Out-Null; $up = $true } catch {}
    if ($up) { Ok "model server running" } else { Warn "model server did not start; run setup again" }
} else {
    Warn "Ollama is not installed. Install it from https://ollama.com/download (or put OllamaSetup.exe in offline\), then run setup again."
}

# ---- 4. Models ----
Step "Models"
$offModels = Join-Path $offline "ollama-models"
if ($SkipModels) {
    Warn "skipped (-SkipModels)"
} elseif (-not $ollama) {
    Warn "skipped: Ollama is not installed"
} else {
    if (Test-Path (Join-Path $offModels "manifests")) {
        Write-Host "   copying models from offline\ollama-models"
        $dest = Join-Path $env:USERPROFILE ".ollama\models"
        robocopy $offModels $dest /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { Warn "model copy reported errors" } else { Ok "models copied" }
    }
    # Downloads whatever is still missing for this machine's hardware; does nothing if all are present.
    & $py -m workbench.doctor --pull
    if ($LASTEXITCODE -ne 0) { Warn "some models are missing. With internet: .venv\Scripts\python -m workbench.doctor --pull" }
}

# ---- 5. Docker sandbox ----
Step "Code sandbox (Docker)"
$image = "workbench-sandbox:1"   # Python with numpy, pandas, sympy
$basic = "python:3.12-slim"      # fallback: standard library only
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        docker image inspect $image *> $null
        if ($LASTEXITCODE -ne 0) {
            $tar = Join-Path $offline "sandbox-image.tar"
            if (Test-Path $tar) {
                docker load -i $tar | Out-Null
            } else {
                Write-Host "   building the sandbox image (needs internet, a few minutes)"
                docker build -q -t $image -f scripts\sandbox.Dockerfile scripts *> $null
            }
        }
        docker image inspect $image *> $null
        if ($LASTEXITCODE -eq 0) {
            Ok "sandbox image ready ($image)"
        } else {
            docker image inspect $basic *> $null
            if ($LASTEXITCODE -ne 0) { docker pull $basic *> $null }
            docker image inspect $basic *> $null
            if ($LASTEXITCODE -eq 0) { Warn "using the basic sandbox image (no numpy, pandas, sympy)" }
            else { Warn "could not get a sandbox image; code will run without isolation" }
        }
    } else {
        Warn "Docker is installed but not running. Start Docker Desktop and run setup again."
    }
} else {
    Warn "Docker Desktop is not installed. The workbench still runs, but code runs without network isolation."
}

# ---- 6. Samples, tests, system check ----
Step "Demo sample files"
& $py samples\make_samples.py

Step "Automated tests"
& $py tests\test_core.py | Select-Object -Last 1
& $py tests\test_api.py | Select-Object -Last 1

Step "System check"
& $py -m workbench.doctor

Write-Host "`nSetup finished. Start the workbench with start.bat. For a full check including the models, run check.bat." -ForegroundColor Cyan
