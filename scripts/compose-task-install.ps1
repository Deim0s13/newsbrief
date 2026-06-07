# Register Compose auto-start and auto-update as Windows Task Scheduler tasks.
# Run once from PowerShell (no admin required):
#   powershell -ExecutionPolicy Bypass -File scripts\compose-task-install.ps1
#
# Or from WSL2:
#   powershell.exe -ExecutionPolicy Bypass -File scripts/compose-task-install.ps1
#
# Tasks registered:
#   "NewsBrief Compose Start" — runs compose-start.sh at login (30s delay)
#   "NewsBrief Compose Watch" — runs compose-watch.sh every hour

$ErrorActionPreference = "Stop"

# Detect WSL distro name — defaults to "Ubuntu"; override with $env:WSL_DISTRO if needed
$WslDistro  = if ($env:WSL_DISTRO) { $env:WSL_DISTRO } else { "Ubuntu" }

# WSL2 path to the project root (adjust if your checkout is elsewhere)
$ProjectDir = "/home/pleathen/projects/newsbrief"

$LogDir = Join-Path (Split-Path -Parent $PSScriptRoot) "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Register-NB {
    param(
        [string]$Name,
        [string]$ScriptRelPath,
        $Trigger
    )

    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue

    # Run via hidden PowerShell so no console window appears (important during gaming/fullscreen)
    $wslCmd  = "wsl.exe -d $WslDistro -- bash $ProjectDir/$ScriptRelPath"
    $psArgs  = "-WindowStyle Hidden -NonInteractive -Command `"$wslCmd`""
    $action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive

    Register-ScheduledTask `
        -TaskName $Name `
        -Action $action `
        -Trigger $Trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "NewsBrief: $Name" | Out-Null

    Write-Host "Registered: $Name"
}

# Task 1: Start Compose stack at login (30s delay to let Podman Desktop initialise first)
$loginTrigger        = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$loginTrigger.Delay  = "PT30S"
Register-NB "NewsBrief Compose Start" "scripts/compose-start.sh" $loginTrigger

# Task 2: Check GHCR for updates once per hour
$repeatTrigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -Once -At (Get-Date)
Register-NB "NewsBrief Compose Watch" "scripts/compose-watch.sh" $repeatTrigger

Write-Host ""
Write-Host "Tasks registered. Test them manually:"
Write-Host "  Start-ScheduledTask 'NewsBrief Compose Start'"
Write-Host "  Start-ScheduledTask 'NewsBrief Compose Watch'"
Write-Host ""
Write-Host "To remove: Unregister-ScheduledTask 'NewsBrief Compose Start','NewsBrief Compose Watch' -Confirm:`$false"
