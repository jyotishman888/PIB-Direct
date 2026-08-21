<#
.SYNOPSIS
  Register a Windows Scheduled Task that runs the PIB pipeline hourly.

.DESCRIPTION
  The APScheduler loop inside `pib-agent serve` only lives as long as that
  process does, so closing the terminal or rebooting silently stops ingestion.
  That is not a cosmetic gap: PIB's listing page shows only the *current day's*
  releases, so a missed hour costs nothing but a missed day is unrecoverable —
  there is no date-filtered fetch to backfill from (the page's date dropdowns
  ignore non-browser postbacks).

  This registers ingestion as a Scheduled Task instead, which survives reboots
  and logouts and does not depend on the web server running at all.

.PARAMETER StartHour / EndHour
  Active window in local time. PIB publishes during the Indian working day, so
  running overnight spends API credits to find nothing.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install-scheduler-task.ps1
  powershell -ExecutionPolicy Bypass -File scripts\install-scheduler-task.ps1 -Remove
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'PIB Direct pipeline',
    [int]$StartHour = 9,
    [int]$EndHour = 21,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $projectRoot '.venv\Scripts\pib-agent.exe'

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "Removed scheduled task '$TaskName'."
    } else {
        Write-Output "No scheduled task named '$TaskName'."
    }
    return
}

if (-not (Test-Path $exe)) {
    throw "pib-agent not found at $exe. Create the virtualenv first (uv sync)."
}
if ($StartHour -lt 0 -or $EndHour -gt 23 -or $StartHour -ge $EndHour) {
    throw "StartHour/EndHour must satisfy 0 <= StartHour < EndHour <= 23."
}

# `run` is the whole pipeline: scrape -> enrich -> notify -> link -> study.
# Run from the project root so the relative sqlite path in .env resolves.
$action = New-ScheduledTaskAction -Execute $exe -Argument 'run' -WorkingDirectory $projectRoot

# Repeat hourly, but only across the active window: the trigger fires at
# StartHour and repeats until EndHour, so nothing runs overnight.
$duration = New-TimeSpan -Hours ($EndHour - $StartHour)
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($StartHour))
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At ([datetime]::Today.AddHours($StartHour)) `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration $duration).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# StartWhenAvailable plus the catch-up above is what recovers a machine that
# was asleep or off at the scheduled minute — the case that loses a whole day.

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Scrape, enrich, notify, link and analyse PIB releases.' `
    -Force | Out-Null

Write-Output "Registered '$TaskName': hourly ${StartHour}:00-${EndHour}:00, running:"
Write-Output "  $exe run   (cwd: $projectRoot)"
Write-Output "Run now with:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "Remove with :  powershell -File scripts\install-scheduler-task.ps1 -Remove"
