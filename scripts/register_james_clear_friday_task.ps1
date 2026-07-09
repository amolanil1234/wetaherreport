# Registers a Windows Task Scheduler job for James Clear 3-2-1 sync every Friday.
# Run: powershell -ExecutionPolicy Bypass -File scripts\register_james_clear_friday_task.ps1

$ErrorActionPreference = "Stop"

$taskName = "JamesClear321FridaySync"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $projectRoot "sync_james_clear_quotes.py"

if (-not (Test-Path $pythonExe)) {
    throw "Python venv not found at $pythonExe. Run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
}

if (-not (Test-Path $scriptPath)) {
    throw "Sync script not found at $scriptPath"
}

$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "`"$scriptPath`" --source web --full" `
    -WorkingDirectory $projectRoot

# Friday 8:00 AM India Standard Time (after typical Thursday US newsletter delivery)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At "8:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Every Friday: sync James Clear 3-2-1 issues from jamesclear.com into data/james_clear_quotes.json" `
    -Force

Write-Host "Registered scheduled task '$taskName' for 8:00 AM every Friday."
Write-Host "Program: $pythonExe"
Write-Host "Arguments: $scriptPath --source web --full"
Write-Host "Working directory: $projectRoot"
Write-Host ""
Write-Host "Test now with: schtasks /Run /TN $taskName"
