# Enforces "nothing leaves this machine" with Windows Firewall: blocks all outbound traffic from
# the model server and the workbench's Python. Traffic between them on this machine (127.0.0.1)
# is not affected. Needs administrator rights; asks for them if missing.
#
#   lockdown.ps1             apply the rules
#   lockdown.ps1 -Remove     remove them
#   lockdown.ps1 -SelfTest   apply, check that the internet is blocked and 127.0.0.1 still works,
#                            then remove again; the result is written to logs\lockdown_selftest.txt
#
# While locked down, model downloads and `pip install` will not work. Unlock first.
param([switch]$Remove, [switch]$SelfTest)

$group = "Sovereign Workbench lockdown"
$root = Split-Path -Parent $PSScriptRoot

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    $extra = ""
    if ($Remove) { $extra = " -Remove" }
    if ($SelfTest) { $extra = " -SelfTest" }
    try {
        Start-Process powershell -Verb RunAs -Wait:$SelfTest -WindowStyle $(if ($SelfTest) { "Hidden" } else { "Normal" }) `
            -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"$extra"
    } catch {
        Write-Host "Administrator rights were not granted: $($_.Exception.Message)" -ForegroundColor Red
        exit 2
    }
    exit
}

function Remove-Rules { Get-NetFirewallRule -Group $group -ErrorAction SilentlyContinue | Remove-NetFirewallRule }

Remove-Rules
if ($Remove) {
    Write-Host "Lockdown removed. Outbound traffic is allowed again." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit
}

$exes = @()
$ollamaDir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
if (Test-Path $ollamaDir) { $exes += (Get-ChildItem $ollamaDir -Recurse -Filter *.exe).FullName }
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $exes += $venvPy
    # A Windows virtual environment starts the base interpreter, so that file must be covered too.
    $exes += (& $venvPy -c "import sys; print(sys._base_executable)")
}
$exes = $exes | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

foreach ($exe in $exes) {
    New-NetFirewallRule -DisplayName "Workbench block: $(Split-Path $exe -Leaf)" -Group $group `
        -Direction Outbound -Action Block -Program $exe -Profile Any | Out-Null
    Write-Host "  blocked outbound: $exe"
}

if ($SelfTest) {
    $probe = @'
import socket, sys
def reach(host, port):
    try:
        socket.create_connection((host, port), timeout=6).close(); return "reached"
    except OSError as e:
        return f"blocked ({e})"
print("internet 1.1.1.1:443 ->", reach("1.1.1.1", 443))
print("this machine 127.0.0.1:11434 (model server) ->", reach("127.0.0.1", 11434))
'@
    $out = @("Lockdown self-test, $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", "rules applied to $($exes.Count) programs:")
    $out += $exes | ForEach-Object { "  $_" }
    $out += "with the rules active, from the workbench's Python:"
    $out += ($probe | & $venvPy -) | ForEach-Object { "  $_" }
    Remove-Rules
    $out += "rules removed again: $(@(Get-NetFirewallRule -Group $group -ErrorAction SilentlyContinue).Count) left"
    New-Item -ItemType Directory -Force (Join-Path $root "logs") | Out-Null
    $out | Set-Content (Join-Path $root "logs\lockdown_selftest.txt") -Encoding utf8
    exit
}

Write-Host "`nLockdown active: $($exes.Count) programs cannot reach the network." -ForegroundColor Green
Write-Host "Check it in the workbench: Network monitor -> Test the firewall lockdown. Undo with unlock.bat."
Read-Host "Press Enter to close"
