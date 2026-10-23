# Fills offline\ so setup.bat can run on a machine with no internet.
# Run on a machine with internet and the same Python version as the target.
param([switch]$Models)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$offline = Join-Path $root "offline"
New-Item -ItemType Directory -Force $offline | Out-Null

Write-Host "== Python packages -> offline\wheels" -ForegroundColor Cyan
& python -m pip download -q --disable-pip-version-check -r requirements.txt -d (Join-Path $offline "wheels")
if ($LASTEXITCODE -ne 0) { Write-Host "   [X] pip download failed" -ForegroundColor Red }

Write-Host "== Sandbox image -> offline\sandbox-image.tar" -ForegroundColor Cyan
docker image inspect workbench-sandbox:1 *> $null
if ($LASTEXITCODE -ne 0) { docker build -q -t workbench-sandbox:1 -f scripts\sandbox.Dockerfile scripts *> $null }
docker save workbench-sandbox:1 -o (Join-Path $offline "sandbox-image.tar")
if ($LASTEXITCODE -ne 0) { Write-Host "   [!] could not save the image (is Docker Desktop running?)" -ForegroundColor Yellow }

Write-Host "== Ollama installer -> offline\OllamaSetup.exe" -ForegroundColor Cyan
$installer = Join-Path $offline "OllamaSetup.exe"
if (-not (Test-Path $installer)) {
    try { Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $installer -UseBasicParsing }
    catch { Write-Host "   [!] download failed: $_" -ForegroundColor Yellow }
}

if ($Models) {
    Write-Host "== Ollama models -> offline\ollama-models (large)" -ForegroundColor Cyan
    $src = Join-Path $env:USERPROFILE ".ollama\models"
    robocopy $src (Join-Path $offline "ollama-models") /E /NFL /NDL /NJH /NJS /NP | Out-Null
} else {
    Write-Host "== Models not copied. Run 'pack_offline.bat -Models' to include them." -ForegroundColor Yellow
}

$pyver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
$size = "{0:N1} GB" -f ((Get-ChildItem $offline -Recurse -File | Measure-Object Length -Sum).Sum / 1GB)
Write-Host "`nDone. offline\ is $size. The target machine needs Python $pyver (64-bit) and, for the sandbox, Docker Desktop." -ForegroundColor Cyan
