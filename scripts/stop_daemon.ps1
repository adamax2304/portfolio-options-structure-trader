param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "OptionsStructureTraderDaemon"
)

$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$scheduledTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($scheduledTask -and $scheduledTask.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
}
$pidFile = Join-Path $resolvedRoot "data\daemon.pid"
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output "No daemon PID file exists; the daemon is not running."
    exit 0
}

$daemonPid = [int](Get-Content -LiteralPath $pidFile -Raw)
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $daemonPid" -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item -LiteralPath $pidFile -Force
    Write-Output "Removed a stale daemon PID file."
    exit 0
}
if ($process.CommandLine -notmatch "options_structure_trader" -or $process.CommandLine -notmatch "daemon") {
    throw "PID $daemonPid does not belong to the Options Structure Trader daemon; nothing was stopped."
}

Stop-Process -Id $daemonPid -PassThru | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $pidFile) {
    Remove-Item -LiteralPath $pidFile -Force
}
Write-Output "Stop signal sent to Options Structure Trader daemon (PID $daemonPid)."
