param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$pidFile = Join-Path $resolvedRoot "data\daemon.pid"
$logDir = Join-Path $resolvedRoot "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

if (Test-Path -LiteralPath $pidFile) {
    $existingPid = [int](Get-Content -LiteralPath $pidFile -Raw)
    if (Get-Process -Id $existingPid -ErrorAction SilentlyContinue) {
        Write-Output "Options Structure Trader daemon is already running (PID $existingPid)."
        exit 0
    }
}

$venvPython = Join-Path $resolvedRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { (Get-Command python.exe).Source }
$stdout = Join-Path $logDir "daemon.stdout.log"
$stderr = Join-Path $logDir "daemon.stderr.log"

$process = Start-Process -FilePath $python -ArgumentList @("-m", "options_structure_trader", "daemon") `
    -WorkingDirectory $resolvedRoot -WindowStyle Hidden -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr -PassThru
Write-Output "Options Structure Trader daemon started in the background (PID $($process.Id))."
