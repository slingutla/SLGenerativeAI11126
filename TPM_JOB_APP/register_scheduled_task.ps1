# One-time setup: register the daily 11 PM PST run with Windows Task Scheduler.
#
# Run this in an ELEVATED PowerShell window (Run as Administrator) ONCE.
# It assumes the machine's local time zone is Pacific (PST/PDT). If your machine
# is in a different time zone, edit $TriggerTime below to the local-clock equivalent
# of 23:00 PST.
#
# To remove the task later:  Unregister-ScheduledTask -TaskName 'TPM_JOB_APP_Daily' -Confirm:$false

$ErrorActionPreference = "Stop"

$TaskName    = "TPM_JOB_APP_Daily"
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunnerPath  = Join-Path $ScriptDir "run_tpm_job_agent.ps1"
$TriggerTime = "23:00"   # 11:00 PM local time

if (-not (Test-Path $RunnerPath)) {
    throw "Runner script not found at $RunnerPath"
}

# Confirm local time zone is Pacific so the trigger matches PST/PDT.
$Tz = (Get-TimeZone).Id
if ($Tz -notmatch "Pacific") {
    Write-Warning "Your machine time zone is '$Tz', not Pacific. The trigger fires at LOCAL 23:00."
    Write-Warning "If you want 11 PM PST regardless of your local zone, edit `$TriggerTime in this script."
}

# Remove any prior version of the task so re-running this script is idempotent.
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing task '$TaskName'..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerPath`"" `
    -WorkingDirectory $ScriptDir

$Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Daily LinkedIn TPM job-digest at 11 PM local. Runs only when the user is logged on." | Out-Null

Write-Host ""
Write-Host "Registered scheduled task '$TaskName'." -ForegroundColor Green
Write-Host "  Trigger:   Daily at $TriggerTime (local time, time zone: $Tz)"
Write-Host "  Action:    $RunnerPath"
Write-Host ""
Write-Host "Test it now with:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Inspect the next run time with:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
