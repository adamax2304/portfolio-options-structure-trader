param(
    [string]$TaskName = "OptionsStructureTraderDaemon",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$venvPython = Join-Path $resolvedRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { (Get-Command python.exe).Source }

$action = New-ScheduledTaskAction -Execute $python -Argument "-m options_structure_trader daemon" `
    -WorkingDirectory $resolvedRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Always-on paper-only Options Structure Trader scheduler" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output "Installed and started Task Scheduler task '$TaskName'."
