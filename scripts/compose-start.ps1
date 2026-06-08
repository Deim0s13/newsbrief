# Start the NewsBrief Compose stack idempotently.
# Called by Windows Task Scheduler at login (30s delay).
# No WSL2 required - runs native Podman Desktop commands.
#
# Manual run (from PowerShell or WSL2):
#   powershell.exe -ExecutionPolicy Bypass -File scripts/compose-start.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$LogDir  = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "compose-start.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ') $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

# Wait for Podman Desktop to finish initialising (up to 60 s)
Log "Waiting for Podman..."
for ($i = 1; $i -le 20; $i++) {
    $null = podman info 2>&1
    if ($LASTEXITCODE -eq 0) { break }
    Log "Podman not ready yet ($i/20)..."
    Start-Sleep 3
}

if ($LASTEXITCODE -ne 0) {
    Log "ERROR: Podman not available after 60 s. Aborting."
    exit 1
}

Log "Podman ready. Starting stack..."
Set-Location $ProjectRoot
podman-compose -f compose.yaml -f compose.windows.yaml up -d

if ($LASTEXITCODE -eq 0) {
    Log "Stack started successfully."
} else {
    Log "ERROR: podman-compose exited with code $LASTEXITCODE."
    exit $LASTEXITCODE
}
