from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


SYMBOL_STATES = {
    "ACTIVE", "DISABLED", "NO_OPTIONS_DATA", "STALE_CANDLES", "PROVIDER_UNAVAILABLE",
    "MACRO_BLOCKED", "LOW_LIQUIDITY", "ERROR_PAUSED",
}


@dataclass(slots=True)
class WatchlistEntry:
    symbol: str
    tier: str
    enabled: bool = True
    priority: int = 50
    sector_theme: str | None = None
    min_price: float = 1.0
    min_avg_volume: float = 250_000
    options_required: bool = True
    free_validation_allowed: bool = True
    production_allowed: bool = True
    notes: str = ""

    @classmethod
    def from_value(cls, tier: str, value: str | dict[str, Any], tier_priority: int) -> "WatchlistEntry":
        if isinstance(value, str):
            return cls(symbol=value.upper(), tier=tier, priority=tier_priority)
        payload = dict(value)
        symbol = str(payload.pop("symbol", payload.pop("ticker", ""))).upper().strip()
        if not symbol:
            raise ValueError(f"Watchlist entry in {tier} is missing symbol")
        if "sector/theme" in payload:
            payload["sector_theme"] = payload.pop("sector/theme")
        priority = int(payload.pop("priority", tier_priority))
        return cls(symbol=symbol, tier=tier, priority=priority, **payload)


class WatchlistManager:
    TIER_INTERVALS = {"tier_1_core": 5, "tier_2_liquid_growth": 10,
                      "tier_3_high_beta_theme": 15, "tier_4_etfs_macro": 15}
    TIER_PRIORITIES = {"tier_1_core": 100, "tier_2_liquid_growth": 75,
                       "tier_3_high_beta_theme": 50, "tier_4_etfs_macro": 40}

    def __init__(self, config_path: Path, status_path: Path, *, failed_cooldown_minutes: int = 30,
                 max_failures_per_day: int = 5):
        self.config_path = config_path
        self.status_path = status_path
        self.failed_cooldown_minutes = failed_cooldown_minutes
        self.max_failures_per_day = max_failures_per_day
        self.entries = self._load()

    def _load(self) -> dict[str, WatchlistEntry]:
        payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        tiers = payload.get("watchlist", {})
        entries: dict[str, WatchlistEntry] = {}
        for tier, values in tiers.items():
            for value in values or []:
                entry = WatchlistEntry.from_value(tier, value, self.TIER_PRIORITIES.get(tier, 25))
                if entry.symbol in entries:
                    raise ValueError(f"Duplicate watchlist symbol: {entry.symbol}")
                entries[entry.symbol] = entry
        return entries

    def entry(self, symbol: str) -> WatchlistEntry | None:
        return self.entries.get(symbol.upper())

    def symbols(self, *, enabled_only: bool = True) -> list[str]:
        values = [entry for entry in self.entries.values() if entry.enabled or not enabled_only]
        return [entry.symbol for entry in sorted(values, key=lambda item: -item.priority)]

    def _read_status(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {"updated_at_utc": None, "symbols": {}}
        try:
            return json.loads(self.status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"updated_at_utc": None, "symbols": {}}

    def status(self) -> dict[str, Any]:
        persisted = self._read_status()
        rows = []
        for entry in sorted(self.entries.values(), key=lambda item: -item.priority):
            state = persisted.get("symbols", {}).get(entry.symbol, {})
            rows.append({**asdict(entry), "status": "DISABLED" if not entry.enabled else state.get("status", "ACTIVE"),
                         "last_scan_time": state.get("last_scan_time"),
                         "last_error": state.get("last_error"),
                         "failures_today": state.get("failures_today", 0),
                         "cooldown_until_utc": state.get("cooldown_until_utc"),
                         "last_outcome": state.get("last_outcome")})
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {"configured_symbols": len(rows), "enabled_symbols": sum(row["enabled"] for row in rows),
                "updated_at_utc": persisted.get("updated_at_utc"), "status_counts": counts,
                "symbols": rows}

    def update_symbol(self, symbol: str, status: str, *, at: datetime, outcome: str | None = None,
                      error: str | None = None, failure: bool = False) -> None:
        if status not in SYMBOL_STATES:
            raise ValueError(f"Unknown symbol status: {status}")
        payload = self._read_status()
        states = payload.setdefault("symbols", {})
        current = states.get(symbol, {})
        today = at.astimezone(timezone.utc).date().isoformat()
        if current.get("failure_date") != today:
            current["failures_today"] = 0
        if failure:
            current["failures_today"] = int(current.get("failures_today", 0)) + 1
            current["failure_date"] = today
            current["cooldown_until_utc"] = (at + timedelta(minutes=self.failed_cooldown_minutes)).isoformat()
            if current["failures_today"] >= self.max_failures_per_day:
                status = "ERROR_PAUSED"
        current.update({"status": status, "last_scan_time": at.isoformat(),
                        "last_outcome": outcome, "last_error": error})
        states[symbol] = current
        payload["updated_at_utc"] = at.isoformat()
        self._atomic_write(payload)

    def is_cooling_down(self, symbol: str, at: datetime) -> bool:
        current = self._read_status().get("symbols", {}).get(symbol, {})
        if int(current.get("failures_today", 0)) >= self.max_failures_per_day:
            return True
        if current.get("status") == "LOW_LIQUIDITY" and current.get("last_scan_time"):
            if datetime.fromisoformat(current["last_scan_time"]).date() == at.astimezone(timezone.utc).date():
                return True
        value = current.get("cooldown_until_utc")
        return bool(value and datetime.fromisoformat(value) > at.astimezone(timezone.utc))

    def due_symbols(self, at: datetime, *, max_symbols: int, cycle_minutes: int = 5) -> list[WatchlistEntry]:
        epoch_slot = int(at.timestamp() // max(cycle_minutes * 60, 1))
        due = []
        for entry in self.entries.values():
            if not entry.enabled or self.is_cooling_down(entry.symbol, at):
                continue
            interval = self.TIER_INTERVALS.get(entry.tier, 15)
            slots = max(1, interval // max(cycle_minutes, 1))
            if epoch_slot % slots == 0:
                due.append(entry)
        return sorted(due, key=lambda item: -item.priority)[:max_symbols]

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_suffix(self.status_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.status_path)
