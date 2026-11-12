# Windows Autostart

The daemon is paper-only. It sleeps outside the valid US market window, wakes after the configured RTH warm-up, scans rotating watchlist batches, and generates the daily report after the exchange close.

## One-time setup

Open PowerShell in the project folder and prepare the local environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Install the per-user Task Scheduler task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_task.ps1
```

The task starts at user login, runs without an open terminal, starts when a login trigger was missed, and retries once per minute after failures. It prefers `.venv\Scripts\python.exe` and falls back to the current `python.exe` only when no project virtual environment exists.

## Manual controls

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop_daemon.ps1
```

To remove autostart and stop the daemon:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_windows_task.ps1
```

## Status and logs

- Dashboard/API status: `/scheduler/status`
- Watchlist readiness: `/watchlist/status`
- Heartbeat state: `data/daemon_status.json`
- Process ID: `data/daemon.pid`
- Rotating daemon log: `logs/daemon.log`
- Manual launcher output: `logs/daemon.stdout.log` and `logs/daemon.stderr.log`
- Daily reports: `reports/YYYY-MM-DD/`

The status and logs never include configured API keys or secrets. If the heartbeat stops changing, run `stop_daemon.ps1`, inspect `logs/daemon.log`, then run `start_daemon.ps1`.
