# Register Compose auto-start and auto-update as Windows Task Scheduler tasks.
# No WSL2 required — tasks invoke native PowerShell scripts directly.
#
# Run once from PowerShell (no admin required):
#   powershell -ExecutionPolicy Bypass -File scripts\compose-task-install.ps1
#
# Or from WSL2:
#   make compose-autostart-install
#
# Tasks registered:
#   "NewsBrief Compose Start" — runs compose-start.ps1 at login (30s delay)
#   "NewsBrief Compose Watch" — runs compose-watch.ps1 once daily at 06:00

$ErrorActionPreference = "Stop"

function Register-NB {
    param(
        [string]$Name,
        [string]$ScriptStem,
        $Trigger
    )

    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue

    # Derive the PS1 path from this installer's own location — portable regardless
    # of whether the repo lives on a Windows path or a \\wsl$\ UNC path.
    $ps1Path = Join-Path $PSScriptRoot ($ScriptStem + ".ps1")
    $psArgs  = "-WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File `"$ps1Path`""
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
$loginTrigger       = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$loginTrigger.Delay = "PT30S"
Register-NB "NewsBrief Compose Start" "compose-start" $loginTrigger

# Task 2: Check GHCR for updates once daily at 06:00 (off-peak, avoids gaming disruption)
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At "06:00"
Register-NB "NewsBrief Compose Watch" "compose-watch" $dailyTrigger

Write-Host ""
Write-Host "Tasks registered. Test them manually:"
Write-Host "  Start-ScheduledTask 'NewsBrief Compose Start'"
Write-Host "  Start-ScheduledTask 'NewsBrief Compose Watch'"
Write-Host ""
Write-Host "Logs: $(Split-Path -Parent $PSScriptRoot)\logs\"
Write-Host "To remove: Unregister-ScheduledTask 'NewsBrief Compose Start','NewsBrief Compose Watch' -Confirm:`$false"
