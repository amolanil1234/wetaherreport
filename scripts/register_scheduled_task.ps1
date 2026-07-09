# Registers a Windows Task Scheduler job for daily weather digest at 7:00 AM IST.
# Run: powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_task.ps1

$ErrorActionPreference = "Stop"

$taskName = "WeatherEmailDigest"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $projectRoot "send_daily_digest.py"

if (-not (Test-Path $pythonExe)) {
    throw "Python venv not found at $pythonExe. Run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
}

if (-not (Test-Path $scriptPath)) {
    throw "Digest script not found at $scriptPath"
}

$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument $scriptPath `
    -WorkingDirectory $projectRoot

# 7:00 AM in India Standard Time
$trigger = New-ScheduledTaskTrigger -Daily -At "7:00AM"

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
    -Description "Daily weather digest for Delhi, Mumbai, Nagpur via Open-Meteo and SendGrid" `
    -Force

Write-Host "Registered scheduled task '$taskName' for 7:00 AM daily."
Write-Host "Program: $pythonExe"
Write-Host "Arguments: $scriptPath"
Write-Host "Working directory: $projectRoot"
Write-Host ""
Write-Host "Test now with: schtasks /Run /TN $taskName"
