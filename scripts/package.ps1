# Makes a clean copy of the project for moving to another machine: dist\sovereign-workbench.zip.
# Leaves out everything that is rebuilt or local: the Python environment, task files, logs,
# the knowledge base, the offline bundle and caches.
# Use -WithOffline to include the offline\ folder (large).
param([switch]$WithOffline)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$stage = Join-Path $env:TEMP ("workbench-package-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$target = Join-Path $stage "sovereign-workbench"
$skip = @(".venv", "workspace", "logs", "data", "dist", "__pycache__", ".git")
if (-not $WithOffline) { $skip += "offline" }

robocopy $root $target /E /XD $skip /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Write-Host "[X] copy failed" -ForegroundColor Red; exit 1 }

$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
$zip = Join-Path $dist "sovereign-workbench.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $target -DestinationPath $zip
Remove-Item $stage -Recurse -Force

$files = (Get-ChildItem $root -Recurse -File | Where-Object { $_.FullName -notmatch "\\(\.venv|workspace|logs|data|dist|offline|__pycache__)\\" }).Count
$size = "{0:N1} MB" -f ((Get-Item $zip).Length / 1MB)
Write-Host "Created $zip ($size, $files files)." -ForegroundColor Cyan
Write-Host "On the other machine: unzip, then run setup.bat, then start.bat. See SETUP.md."
