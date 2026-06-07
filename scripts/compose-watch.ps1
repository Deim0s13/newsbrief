# Check GHCR for a newer image; redeploy + migrate if one is found.
# Called by Windows Task Scheduler once daily at 06:00.
# No WSL2 required — runs native Podman Desktop commands.
#
# Manual run (from PowerShell or WSL2):
#   powershell.exe -ExecutionPolicy Bypass -File scripts/compose-watch.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$LogDir  = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "compose-watch.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ') $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

# Load .env to pick up NTFY_TOPIC (fail silently if absent)
$NtfyTopic = $null
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*?)\s*=\s*"?(.*?)"?\s*$') {
            $key   = $matches[1].Trim()
            $value = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
            if ($key -eq "NTFY_TOPIC") { $NtfyTopic = $value }
        }
    }
}

# Wait for Podman (may be called right after boot)
for ($i = 1; $i -le 10; $i++) {
    $null = podman info 2>&1
    if ($LASTEXITCODE -eq 0) { break }
    Log "Waiting for Podman... ($i/10)"
    Start-Sleep 3
}

if ($LASTEXITCODE -ne 0) {
    Log "Podman not available. Skipping update check."
    exit 0
}

Set-Location $ProjectRoot

$Image = "ghcr.io/deim0s13/newsbrief:latest"

# SHA256 of the image the running container is using
$RunningId = podman inspect newsbrief --format '{{.Image}}' 2>$null
if ($LASTEXITCODE -ne 0) { $RunningId = "" }

Log "Pulling $Image..."
$null = podman pull $Image --quiet 2>&1
if ($LASTEXITCODE -ne 0) {
    Log "Could not pull image (offline?). Skipping."
    exit 0
}

$LatestId = podman image inspect $Image --format '{{.Id}}' 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($LatestId)) {
    Log "Could not determine latest image ID. Skipping."
    exit 0
}

if ($RunningId -eq $LatestId) {
    Log "Already at latest ($LatestId). No action needed."
    exit 0
}

Log "New image detected ($LatestId). Deploying..."
podman-compose -f compose.yaml -f compose.prod.yaml up -d
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: podman-compose up failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Log "Waiting for database..."
while ($true) {
    $null = podman exec newsbrief-db pg_isready -U newsbrief -d newsbrief 2>&1
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep 2
}

Log "Running migrations..."
podman-compose -f compose.yaml -f compose.prod.yaml exec -T api alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: alembic upgrade failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Log "Deploy complete: $LatestId"

if ($NtfyTopic) {
    try {
        Invoke-RestMethod -Method Post `
            -Uri "https://ntfy.sh/$NtfyTopic" `
            -Headers @{ Title = "NewsBrief auto-deployed"; Priority = "default" } `
            -Body "New version deployed on $env:COMPUTERNAME" | Out-Null
    } catch {
        Log "ntfy notification failed (non-fatal): $_"
    }
}
