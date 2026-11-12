param(
    [string]$TaskName = "OptionsStructureTraderDaemon",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed Task Scheduler task '$TaskName'."
} else {
    Write-Output "Task Scheduler task '$TaskName' is not installed."
}
& (Join-Path $PSScriptRoot "stop_daemon.ps1") -ProjectRoot $ProjectRoot
