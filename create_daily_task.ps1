param(
    [string]$TaskName = "JobTrackerDaily",
    [string]$ScriptPath = "$PSScriptRoot\run_all.ps1",
    [string]$TriggerTime = "09:00"
)

# Create an action to run PowerShell and execute the script
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""

# Daily trigger
$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date -Hour ([int]$TriggerTime.Split(':')[0]) -Minute ([int]$TriggerTime.Split(':')[1]))

# Register the scheduled task
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "Runs Job-Post-Email-Tracker daily" -User "$env:USERNAME" -RunLevel Highest

Write-Output "Scheduled task '$TaskName' created to run $ScriptPath daily at $TriggerTime."