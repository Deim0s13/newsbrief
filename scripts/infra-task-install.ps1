# Register infra-start.ps1 as a Windows Task Scheduler task.
# Run once from PowerShell (as your user, no admin needed):
#   powershell -ExecutionPolicy Bypass -File scripts\infra-task-install.ps1
#
# Or from WSL2:
#   powershell.exe -ExecutionPolicy Bypass -File scripts/infra-task-install.ps1

$TaskName   = "NewsBrief Infrastructure"
$ScriptPath = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\infra-start.ps1"
$LogDir     = Join-Path (Split-Path -Parent $PSScriptRoot) "logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Remove existing task if present
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""

# Trigger: at log on for the current user
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Run with highest privileges so kind/kubectl can manage the cluster
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Start kind cluster, ArgoCD, and kubectl port-forwards for NewsBrief on login" | Out-Null

Write-Host "✅ Task Scheduler task registered: '$TaskName'"
Write-Host "   Script: $ScriptPath"
Write-Host "   Trigger: At log on ($env:USERNAME)"
Write-Host ""
Write-Host "The NewsBrief infrastructure will start automatically on your next login."
Write-Host "To run it now: Start-ScheduledTask -TaskName '$TaskName'"
