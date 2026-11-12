from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from collections import Counter
from statistics import median
from typing import Any

import pandas as pd
from zoneinfo import ZoneInfo

from .db import Repository
from .models import Mode, ReplayRequest, ScanInput, SetupEvent, new_id


class PerformanceReporter:
    def __init__(self, repository: Repository):
        self.repository = repository

    def summary(self, mode: Mode = Mode.PRODUCTION, setup_type: str | None = None) -> dict[str, Any]:
        where, params = "WHERE mode=?", [mode.value]
        if setup_type:
            where += " AND setup_type=?"
            params.append(setup_type)
        trades = self.repository.list_json("paper_trades", where, tuple(params), limit=100000)
        closed = [item for item in trades if item["status"] == "closed"]
        returns = [float(item.get("realized_r", 0)) for item in closed]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        equity, peak, max_drawdown = 0.0, 0.0, 0.0
        for value in reversed(returns):
            equity += value
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        return {
            "mode": mode.value, "setup_type": setup_type or "ALL", "sample_size": len(closed),
            "expectancy_R": round(sum(returns) / len(returns), 4) if returns else 0,
            "win_rate": round(len(wins) / len(returns), 4) if returns else 0,
            "profit_factor": round(sum(wins) / abs(sum(losses)), 4) if losses else (None if not wins else "infinite"),
            "avg_win_R": round(sum(wins) / len(wins), 4) if wins else 0,
            "avg_loss_R": round(sum(losses) / len(losses), 4) if losses else 0,
            "max_drawdown_R": round(max_drawdown, 4),
            "median_MFE_R": round(median([item.get("mfe_r", 0) for item in closed]), 4) if closed else 0,
            "median_MAE_R": round(median([item.get("mae_r", 0) for item in closed]), 4) if closed else 0,
            "open_count": len([item for item in trades if item["status"] in {"pending", "open", "partial"}]),
        }

    def by_setup(self, mode: Mode = Mode.PRODUCTION) -> list[dict[str, Any]]:
        trades = self.repository.list_json("paper_trades", "WHERE mode=?", (mode.value,), limit=100000)
        names = sorted({item["setup_type"] for item in trades})
        return [self.summary(mode, name) for name in names]

    def export(self, output_dir: Path) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        exported: dict[str, str] = {}
        for table in ("setup_events", "paper_trades", "paper_trade_variants", "option_levels"):
            rows = self.repository.list_json(table, limit=100000)
            frame = pd.json_normalize(rows)
            # Parquet requires a stable type per column. Variant payloads intentionally mix
            # numeric and named values, so object columns are serialized deterministically.
            for column in frame.columns:
                if frame[column].dtype == object or isinstance(frame[column].dtype, pd.StringDtype):
                    frame[column] = frame[column].map(
                        lambda value: json.dumps(value, sort_keys=True, default=str)
                        if isinstance(value, (dict, list, tuple)) else
                        (None if value is None else str(value))
                    )
            csv_path, parquet_path = output_dir / f"{table}.csv", output_dir / f"{table}.parquet"
            frame.to_csv(csv_path, index=False)
            frame.to_parquet(parquet_path, index=False)
            exported[f"{table}_csv"] = str(csv_path)
            exported[f"{table}_parquet"] = str(parquet_path)
        return exported


class ReplayRunner:
    def __init__(self, detector: Any):
        self.detector = detector

    def run(self, request: ReplayRequest) -> dict[str, Any]:
        ordered = sorted(request.snapshots, key=lambda item: item.confirmation_bar.bar_end_utc)
        setups: list[SetupEvent] = []
        rejected_lookahead = 0
        for snapshot in ordered:
            if snapshot.level.known_at_utc >= snapshot.confirmation_bar.bar_start_utc:
                rejected_lookahead += 1
                continue
            setup = self.detector.detect(snapshot, at=snapshot.confirmation_bar.bar_end_utc)
            if setup:
                setups.append(setup)
        digest_input = json.dumps({
            "inputs": [item.model_dump(mode="json") for item in ordered],
            "detected": [{"ticker": item.ticker, "setup_type": item.setup_type.value,
                          "side": item.side.value, "score": item.score.total,
                          "trade_plan": item.trade_plan.model_dump(mode="json") if item.trade_plan else None,
                          "blocking_reasons": item.blocking_reasons} for item in setups],
            "lookahead_rejections": rejected_lookahead,
        }, sort_keys=True, separators=(",", ":"))
        import hashlib
        return {"run_id": new_id("replay"), "snapshots_processed": len(ordered),
                "setups_detected": len(setups), "lookahead_rejections": rejected_lookahead,
                "determinism_hash": hashlib.sha256(digest_input.encode()).hexdigest(),
                "setups": [item.model_dump(mode="json") for item in setups]}


class TradeManagementResearch:
    """Counterfactual paper-trade management replay.

    This reads canonical setup/trade/bar history and writes separate research artifacts.
    It intentionally does not mutate paper_trades or setup_events.
    """

    THRESHOLDS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]

    def __init__(self, repository: Repository, settings: Any, watchlist: Any, output_root: Path):
        self.repository = repository
        self.settings = settings
        self.watchlist = watchlist
        self.output_root = output_root

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return default if value is None else float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _score_bucket(value: Any) -> str:
        score = TradeManagementResearch._safe_float(value, -1)
        if score < 50:
            return "<50"
        if score < 60:
            return "50-59"
        if score < 70:
            return "60-69"
        if score < 80:
            return "70-79"
        if score < 90:
            return "80-89"
        return "90+"

    @staticmethod
    def _confidence_bucket(value: Any) -> str:
        confidence = TradeManagementResearch._safe_float(value, 0)
        if confidence < 0.35:
            return "<0.35"
        if confidence < 0.50:
            return "0.35-0.49"
        if confidence < 0.65:
            return "0.50-0.64"
        if confidence < 0.80:
            return "0.65-0.79"
        return "0.80+"

    @staticmethod
    def _sample_label(n: int) -> str:
        if n < 20:
            return "INSUFFICIENT_SAMPLE"
        if n < 50:
            return "exploratory"
        return "usable_preliminary_evidence"

    @staticmethod
    def _natural(payload: dict[str, Any]) -> bool:
        text = json.dumps(payload, sort_keys=True, default=str).lower()
        return "demo_fixture" not in text and '"synthetic_present": true' not in text and '"fixture": true' not in text

    def _closed_natural(self) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        setups = self.repository.list_json("setup_events", limit=100000)
        setup_by_id = {setup["setup_event_id"]: setup for setup in setups}
        trades = self.repository.list_json("paper_trades", limit=100000)
        closed = [trade for trade in trades if trade.get("status") == "closed"
                  and setup_by_id.get(trade.get("setup_event_id"))
                  and self._natural(setup_by_id[trade["setup_event_id"]])]
        return closed, setup_by_id

    def _bars(self, ticker: str, start_at: datetime, end_at: datetime | None = None) -> list[dict[str, Any]]:
        rows = self.repository.list_json("market_bars", "WHERE ticker=? AND timeframe=?",
                                         (ticker.upper(), "5m"), limit=100000)
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            bar_end = self._parse_time(row.get("bar_end_utc"))
            if not bar_end or bar_end <= start_at:
                continue
            if end_at and bar_end > end_at:
                continue
            unique[row["bar_end_utc"]] = row
        return [unique[key] for key in sorted(unique)]

    def _rth_close(self, opened_at: datetime) -> datetime:
        eastern = ZoneInfo("America/New_York")
        local = opened_at.astimezone(eastern)
        close_local = datetime.combine(local.date(), time(16, 0), eastern)
        return close_local.astimezone(timezone.utc)

    def _variant_specs(self, trade: dict[str, Any]) -> list[dict[str, Any]]:
        entry = self._safe_float(trade.get("actual_fill_price") or trade.get("planned_entry"))
        stop = self._safe_float(trade.get("stop_initial"))
        risk = abs(entry - stop)
        side_mult = 1 if trade.get("side") == "LONG" else -1
        targets = list(trade.get("targets") or [])

        def price_at_r(value: float) -> float:
            return entry + side_mult * risk * value

        tp1 = targets[0] if len(targets) > 0 else price_at_r(1.0)
        tp2 = targets[1] if len(targets) > 1 else price_at_r(1.5)
        tp3 = targets[2] if len(targets) > 2 else price_at_r(2.0)
        current_partial = self._safe_float((self.settings.get("targets.partials", [.33]) or [.33])[0], .33)
        return [
            {"version": "TM_V0_CURRENT", "name": "Variant A current TP1 partial + immediate BE",
             "targets": [(tp1, current_partial, "TP1_PARTIAL")], "be_after": "TP1",
             "time_exit": True, "repeat_last_target": True},
            {"version": "TM_V1_SCALEOUT_33_33_34", "name": "Variant B 33/33/34 BE after TP2",
             "targets": [(tp1, .33, "TP1_PARTIAL"), (tp2, .33, "TP2_PARTIAL"), (tp3, .34, "TP3_EXIT")],
             "be_after": "TP2", "time_exit": True},
            {"version": "TM_V2_SCALEOUT_50_25_25", "name": "Variant C 50% TP1 + runner BE after TP1",
             "targets": [(tp1, .50, "TP1_PARTIAL"), (tp2, .25, "TP2_PARTIAL"), (tp3, .25, "TP3_EXIT")],
             "be_after": "TP2", "time_exit": True},
            {"version": "TM_V3_TP1_PLUS_RUNNER", "name": "Variant C 50% TP1 + 50% runner BE after TP1",
             "targets": [(tp1, .50, "TP1_PARTIAL"), (tp3, .50, "RUNNER_EXIT")],
             "be_after": "TP1", "time_exit": True},
            {"version": "TM_V4_FIXED_1_5R", "name": "Variant D full exit at 1.5R",
             "targets": [(price_at_r(1.5), 1.0, "TP3_EXIT")], "be_after": None, "time_exit": True},
            {"version": "TM_V4_FIXED_2R", "name": "Variant E full exit at 2R",
             "targets": [(price_at_r(2.0), 1.0, "TP3_EXIT")], "be_after": None, "time_exit": True},
            {"version": "TM_V5_STRUCTURE_TARGETS_NO_BE", "name": "Variant F structure targets no immediate BE",
             "targets": [(tp1, .33, "TP1_PARTIAL"), (tp2, .33, "TP2_PARTIAL"), (tp3, .34, "TP3_EXIT")],
             "be_after": None, "time_exit": True},
            {"version": "TM_V6_STRUCTURE_TARGETS_DELAYED_BE", "name": "Variant G structure targets delayed BE",
             "targets": [(tp1, .33, "TP1_PARTIAL"), (tp2, .33, "TP2_PARTIAL"), (tp3, .34, "TP3_EXIT")],
             "be_after": "TP2_OR_1R", "time_exit": True},
        ]

    def _simulate(self, trade: dict[str, Any], setup: dict[str, Any], spec: dict[str, Any],
                  bars: list[dict[str, Any]]) -> dict[str, Any]:
        entry = self._safe_float(trade.get("actual_fill_price") or trade.get("planned_entry"))
        stop_initial = self._safe_float(trade.get("stop_initial"))
        risk = abs(entry - stop_initial)
        side_mult = 1 if trade.get("side") == "LONG" else -1
        opened = self._parse_time(trade.get("opened_at_utc") or trade.get("created_at_utc"))
        remaining = 1.0
        stop = stop_initial
        cumulative = 0.0
        mfe = 0.0
        mae = 0.0
        target_index = 0
        events: list[dict[str, Any]] = [{
            "event_type": "ENTRY", "timestamp": opened.isoformat() if opened else None, "price": entry,
            "quantity_fraction": 1.0, "realized_r_event": 0.0, "cumulative_r": 0.0,
            "remaining_fraction": remaining, "remaining_risk": remaining, "reason": "historical_entry_snapshot"}]

        def target_hit(bar: dict[str, Any], target: float) -> bool:
            return self._safe_float(bar.get("high")) >= target if side_mult == 1 else self._safe_float(bar.get("low")) <= target

        def stop_hit(bar: dict[str, Any]) -> bool:
            return self._safe_float(bar.get("low")) <= stop if side_mult == 1 else self._safe_float(bar.get("high")) >= stop

        def leg_r(price: float, fraction: float) -> float:
            return (((price - entry) * side_mult) / risk * fraction) if risk else 0.0

        for bar in bars:
            high = self._safe_float(bar.get("high"))
            low = self._safe_float(bar.get("low"))
            favorable = high - entry if side_mult == 1 else entry - low
            adverse = entry - low if side_mult == 1 else high - entry
            if risk:
                mfe = max(mfe, favorable / risk)
                mae = max(mae, adverse / risk)
            if remaining <= 0:
                break
            if stop_hit(bar):
                event_type = "BREAKEVEN_EXIT" if abs(stop - entry) <= 0.01 else "STOP_EXIT"
                realized = leg_r(stop, remaining)
                cumulative += realized
                events.append({"event_type": event_type, "timestamp": bar["bar_end_utc"], "price": stop,
                               "quantity_fraction": round(remaining, 6), "realized_r_event": round(realized, 6),
                               "cumulative_r": round(cumulative, 6), "remaining_fraction": 0,
                               "remaining_risk": 0, "reason": "pessimistic_stop_before_target"})
                remaining = 0
                break
            while remaining > 0 and target_index < len(spec["targets"]) and target_hit(bar, spec["targets"][target_index][0]):
                target_price, fraction, event_type = spec["targets"][target_index]
                close_fraction = min(remaining, fraction if not spec.get("repeat_last_target") else max(fraction, min(fraction, remaining)))
                realized = leg_r(target_price, close_fraction)
                cumulative += realized
                remaining = round(max(0.0, remaining - close_fraction), 6)
                events.append({"event_type": event_type, "timestamp": bar["bar_end_utc"], "price": target_price,
                               "quantity_fraction": round(close_fraction, 6), "realized_r_event": round(realized, 6),
                               "cumulative_r": round(cumulative, 6), "remaining_fraction": remaining,
                               "remaining_risk": round(remaining if abs(stop-entry) > 0.01 else 0, 6),
                               "reason": spec["name"]})
                stop_move = False
                if spec.get("be_after") == "TP1" and event_type == "TP1_PARTIAL":
                    stop_move = True
                if spec.get("be_after") == "TP2" and event_type in {"TP2_PARTIAL", "TP3_EXIT"}:
                    stop_move = True
                if spec.get("be_after") == "TP2_OR_1R" and (mfe >= 1.0 or event_type in {"TP2_PARTIAL", "TP3_EXIT"}):
                    stop_move = True
                if stop_move and ((side_mult == 1 and stop < entry) or (side_mult == -1 and stop > entry)):
                    stop = entry
                    events.append({"event_type": "STOP_MOVE", "timestamp": bar["bar_end_utc"], "price": stop,
                                   "quantity_fraction": 0, "realized_r_event": 0.0,
                                   "cumulative_r": round(cumulative, 6), "remaining_fraction": remaining,
                                   "remaining_risk": 0, "reason": f"{spec['version']} breakeven rule"})
                if remaining <= 0:
                    break
                if spec.get("repeat_last_target"):
                    if target_index >= len(spec["targets"]) - 1:
                        break
                else:
                    target_index += 1
            if not spec.get("repeat_last_target") and target_index < len(spec["targets"]) and remaining <= 0:
                break
        if remaining > 0 and bars and spec.get("time_exit"):
            price = self._safe_float(bars[-1].get("close"))
            realized = leg_r(price, remaining)
            cumulative += realized
            events.append({"event_type": "TIME_EXIT", "timestamp": bars[-1]["bar_end_utc"], "price": price,
                           "quantity_fraction": round(remaining, 6), "realized_r_event": round(realized, 6),
                           "cumulative_r": round(cumulative, 6), "remaining_fraction": 0,
                           "remaining_risk": 0, "reason": "available_history_end"})
            remaining = 0
        return {"events": events, "final_r": round(cumulative, 6), "mfe_r": round(mfe, 6),
                "mae_r": round(mae, 6), "event_count": len(events), "final_event": events[-1]["event_type"]}

    def _stats(self, rows: list[dict[str, Any]], dimension: str, bucket: str) -> dict[str, Any]:
        values = [self._safe_float(row.get("final_r")) for row in rows]
        wins = [value for value in values if value > 0.05]
        losses = [value for value in values if value < -0.05]
        equity = peak = max_dd = 0.0
        for value in values:
            equity += value
            peak = max(peak, equity)
            max_dd = max(max_dd, peak-equity)
        return {"dimension": dimension, "bucket": bucket, "n": len(rows),
                "sample_label": self._sample_label(len(rows)),
                "win_rate": round(len(wins)/len(values), 4) if values else 0,
                "expectancy": round(sum(values)/len(values), 4) if values else 0,
                "median_r": round(median(values), 4) if values else 0,
                "total_r": round(sum(values), 4),
                "profit_factor": round(sum(wins)/abs(sum(losses)), 4) if losses else (None if not wins else "infinite"),
                "max_drawdown": round(max_dd, 4),
                "average_winner": round(sum(wins)/len(wins), 4) if wins else 0,
                "average_loser": round(sum(losses)/len(losses), 4) if losses else 0,
                "mfe": round(sum(self._safe_float(row.get("mfe_r")) for row in rows)/len(rows), 4) if rows else 0,
                "mae": round(sum(self._safe_float(row.get("mae_r")) for row in rows)/len(rows), 4) if rows else 0}

    def generate(self) -> dict[str, Any]:
        closed, setup_by_id = self._closed_natural()
        replay_events: list[dict[str, Any]] = []
        final_rows: list[dict[str, Any]] = []
        mfe_rows: list[dict[str, Any]] = []
        entry_rows: list[dict[str, Any]] = []
        stop_rows: list[dict[str, Any]] = []
        counterfactual_rows: list[dict[str, Any]] = []
        actual_values = [self._safe_float(trade.get("realized_r")) for trade in closed]
        for trade in closed:
            setup = setup_by_id[trade["setup_event_id"]]
            opened = self._parse_time(trade.get("opened_at_utc") or trade.get("created_at_utc"))
            if not opened:
                continue
            bars_to_close = self._bars(trade["ticker"], opened, self._parse_time(trade.get("closed_at_utc")))
            bars_forward = self._bars(trade["ticker"], opened, self._rth_close(opened))
            snapshot = setup.get("signal_snapshot") or {}
            eligibility = snapshot.get("eligibility") or {}
            level = snapshot.get("level") or {}
            score = setup.get("score") or {}
            watch = self.watchlist.entry(trade.get("ticker", ""))
            common = {"trade_id": trade["trade_id"], "setup_event_id": trade["setup_event_id"],
                      "symbol": trade["ticker"], "direction": trade["side"],
                      "tier": watch.tier if watch else "unknown",
                      "score_bucket": self._score_bucket(trade.get("score_total")),
                      "confidence_bucket": self._confidence_bucket(score.get("confidence_score")),
                      "gamma_regime": (snapshot.get("features") or {}).get("raw", {}).get("gamma_regime", "unknown"),
                      "distance_from_gamma_flip": None,
                      "level_type": setup.get("level_type") or level.get("level_type"),
                      "candle_provider": eligibility.get("price_provider"),
                      "data_quality": score.get("data_quality_tier")}
            for spec in self._variant_specs(trade):
                replay = self._simulate(trade, setup, spec, bars_to_close)
                final = {**common, "trade_management_version": spec["version"], "variant_name": spec["name"],
                         "final_r": replay["final_r"], "mfe_r": replay["mfe_r"], "mae_r": replay["mae_r"],
                         "event_count": replay["event_count"], "final_event": replay["final_event"],
                         "actual_realized_r": self._safe_float(trade.get("realized_r"))}
                final_rows.append(final)
                for index, event in enumerate(replay["events"], start=1):
                    replay_events.append({**common, "trade_management_version": spec["version"],
                                          "variant_name": spec["name"], "event_sequence": index,
                                          "final_trade_r": replay["final_r"], **event})
            entry = self._safe_float(trade.get("actual_fill_price") or trade.get("planned_entry"))
            stop = self._safe_float(trade.get("stop_initial"))
            risk = abs(entry-stop)
            mfe = self._safe_float(trade.get("mfe_r"))
            mae = self._safe_float(trade.get("mae_r"))
            targets = list(trade.get("targets") or [])
            mfe_rows.append({**common, "actual_realized_r": self._safe_float(trade.get("realized_r")),
                             "mfe_r": mfe, "mae_r": mae,
                             **{f"reached_{str(th).replace('.', '_')}r": mfe >= th for th in self.THRESHOLDS},
                             "tp1_touched": bool(targets) and risk and mfe >= abs(self._safe_float(targets[0])-entry)/risk,
                             "tp2_touched": len(targets) > 1 and risk and mfe >= abs(self._safe_float(targets[1])-entry)/risk,
                             "tp3_touched": len(targets) > 2 and risk and mfe >= abs(self._safe_float(targets[2])-entry)/risk})
            for threshold in [0.5, 1.0, 1.5, 2.0]:
                counterfactual_rows.append({**common, "counterfactual": f"exit_at_{threshold}R",
                                            "counterfactual_r": threshold if mfe >= threshold else self._safe_float(trade.get("realized_r")),
                                            "actual_realized_r": self._safe_float(trade.get("realized_r"))})
            stopout = str(trade.get("exit_reason")) == "stop_loss"
            after_stop = self._bars(trade["ticker"], self._parse_time(trade.get("closed_at_utc")) or opened,
                                    (self._parse_time(trade.get("closed_at_utc")) or opened) + timedelta(minutes=30))
            side_mult = 1 if trade["side"] == "LONG" else -1
            reclaimed_after = any((self._safe_float(bar.get("high")) >= entry if side_mult == 1
                                   else self._safe_float(bar.get("low")) <= entry) for bar in after_stop)
            stop_rows.append({**common, "exit_reason": trade.get("exit_reason"), "stopout": stopout,
                              "went_positive_first": mfe > 0, "reached_0_5r_before_stop": stopout and mfe >= .5,
                              "reached_1r_before_stop": stopout and mfe >= 1.0, "mae_r": mae,
                              "stop_distance": risk, "stop_distance_pct": round(risk/entry, 6) if entry else None,
                              "reclaimed_within_30m_after_stop": bool(stopout and reclaimed_after)})
            for label, minutes in [("15m", 15), ("30m", 30), ("60m", 60), ("120m", 120),
                                   ("end_of_rth", None)]:
                horizon_end = self._rth_close(opened) if minutes is None else opened + timedelta(minutes=minutes)
                horizon_bars = [bar for bar in bars_forward if self._parse_time(bar["bar_end_utc"]) <= horizon_end]
                if not horizon_bars:
                    continue
                high = max(self._safe_float(bar.get("high")) for bar in horizon_bars)
                low = min(self._safe_float(bar.get("low")) for bar in horizon_bars)
                close = self._safe_float(horizon_bars[-1].get("close"))
                mfe_h = ((high-entry) if side_mult == 1 else (entry-low)) / risk if risk else 0
                mae_h = ((entry-low) if side_mult == 1 else (high-entry)) / risk if risk else 0
                entry_rows.append({**common, "horizon": label, "horizon_complete": self._parse_time(horizon_bars[-1]["bar_end_utc"]) >= horizon_end,
                                   "forward_return": round(((close-entry)*side_mult)/entry, 6) if entry else 0,
                                   "max_favorable_excursion_r": round(mfe_h, 4),
                                   "max_adverse_excursion_r": round(mae_h, 4),
                                   "prob_0_5r_before_minus_1r_sample": mfe_h >= .5 and mae_h < 1,
                                   "prob_1r_before_minus_1r_sample": mfe_h >= 1 and mae_h < 1,
                                   "prob_2r_before_minus_1r_sample": mfe_h >= 2 and mae_h < 1})

        variant_summaries = [self._stats([row for row in final_rows if row["trade_management_version"] == version],
                                         "variant", version)
                             for version in sorted({row["trade_management_version"] for row in final_rows})]
        segment_rows: list[dict[str, Any]] = []
        for version in sorted({row["trade_management_version"] for row in final_rows}):
            version_rows = [row for row in final_rows if row["trade_management_version"] == version]
            segment_rows.append(self._stats(version_rows, "overall", version))
            for dimension in ["direction", "symbol", "tier", "score_bucket", "confidence_bucket", "gamma_regime",
                              "distance_from_gamma_flip", "level_type", "candle_provider", "data_quality"]:
                grouped: dict[str, list[dict[str, Any]]] = {}
                for row in version_rows:
                    grouped.setdefault(str(row.get(dimension) or "unknown"), []).append(row)
                for bucket, rows in sorted(grouped.items()):
                    item = self._stats(rows, dimension, bucket)
                    item["trade_management_version"] = version
                    segment_rows.append(item)

        def frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
            return pd.DataFrame(rows).map(lambda value: json.dumps(value, sort_keys=True, default=str)
                                          if isinstance(value, (dict, list, tuple)) else value)

        replay_path = self.output_root / "trade_management_replay.csv"
        mfe_path = self.output_root / "mfe_threshold_analysis.csv"
        entry_path = self.output_root / "entry_edge_analysis.csv"
        stop_path = self.output_root / "stop_efficiency_analysis.csv"
        segment_path = self.output_root / "trade_management_segment_summary.csv"
        counterfactual_path = self.output_root / "counterfactual_exit_analysis.csv"
        frame(replay_events).to_csv(replay_path, index=False)
        frame(mfe_rows).to_csv(mfe_path, index=False)
        frame(entry_rows).to_csv(entry_path, index=False)
        frame(stop_rows).to_csv(stop_path, index=False)
        frame(segment_rows).to_csv(segment_path, index=False)
        frame(counterfactual_rows).to_csv(counterfactual_path, index=False)

        best = max(variant_summaries, key=lambda row: row["expectancy"], default={})
        baseline = next((row for row in variant_summaries if row["bucket"] == "TM_V0_CURRENT"), {})
        threshold_rates = {f"pct_reaching_{threshold}R": round(sum(row.get(f"reached_{str(threshold).replace('.', '_')}r", False)
                                                                  for row in mfe_rows) / len(mfe_rows), 4)
                           if mfe_rows else 0 for threshold in self.THRESHOLDS}
        count = lambda pred: sum(1 for row in mfe_rows if pred(row))
        conditional = {
            "p_1r_given_0_5r": round(count(lambda row: row.get("reached_1_0r")) / count(lambda row: row.get("reached_0_5r")), 4)
            if count(lambda row: row.get("reached_0_5r")) else 0,
            "p_1_5r_given_1r": round(count(lambda row: row.get("reached_1_5r")) / count(lambda row: row.get("reached_1_0r")), 4)
            if count(lambda row: row.get("reached_1_0r")) else 0,
            "p_2r_given_1r": round(count(lambda row: row.get("reached_2_0r")) / count(lambda row: row.get("reached_1_0r")), 4)
            if count(lambda row: row.get("reached_1_0r")) else 0,
        }
        be_exits = sum(1 for trade in closed if trade.get("exit_reason") == "breakeven_stop")
        tp1_exits = sum(1 for trade in closed if trade.get("exit_reason") == "tp1")
        setups = [setup for setup in setup_by_id.values() if self._natural(setup)]
        free_blockers = Counter(reason for setup in setups for reason in (setup.get("free_validation_blocking_reasons") or []))
        routing_lines = "\n".join(f"| {reason} | {count} |" for reason, count in free_blockers.most_common(8)) or "| none | 0 |"
        segment_lines = "\n".join(
            f"| {row.get('trade_management_version', row['bucket'])} | {row['dimension']} | {row['bucket']} | {row['n']} | {row['expectancy']} | {row['profit_factor']} | {row['sample_label']} |"
            for row in segment_rows
            if row["dimension"] in {"direction", "score_bucket", "level_type"} and row["n"] >= 20
        ) or "| none | none | none | 0 | 0 | 0 | INSUFFICIENT_SAMPLE |"
        entry_summary_rows = []
        for horizon in ["15m", "30m", "60m", "120m", "end_of_rth"]:
            rows = [row for row in entry_rows if row["horizon"] == horizon]
            if rows:
                entry_summary_rows.append({
                    "horizon": horizon, "n": len(rows),
                    "avg_forward_return": round(sum(row["forward_return"] for row in rows)/len(rows), 6),
                    "avg_mfe": round(sum(row["max_favorable_excursion_r"] for row in rows)/len(rows), 4),
                    "avg_mae": round(sum(row["max_adverse_excursion_r"] for row in rows)/len(rows), 4),
                    "p_0_5_before_minus_1": round(sum(row["prob_0_5r_before_minus_1r_sample"] for row in rows)/len(rows), 4),
                    "p_1_before_minus_1": round(sum(row["prob_1r_before_minus_1r_sample"] for row in rows)/len(rows), 4),
                    "p_2_before_minus_1": round(sum(row["prob_2r_before_minus_1r_sample"] for row in rows)/len(rows), 4),
                })
        entry_lines = "\n".join(
            f"| {row['horizon']} | {row['n']} | {row['avg_forward_return']} | {row['avg_mfe']} | {row['avg_mae']} | {row['p_0_5_before_minus_1']:.1%} | {row['p_1_before_minus_1']:.1%} | {row['p_2_before_minus_1']:.1%} |"
            for row in entry_summary_rows
        ) or "| none | 0 | 0 | 0 | 0 | 0% | 0% | 0% |"
        winners_stop = [row["mae_r"] for row in stop_rows
                        if self._safe_float(next((trade.get("realized_r") for trade in closed if trade["trade_id"] == row["trade_id"]), 0)) > .05]
        losers_stop = [row["mae_r"] for row in stop_rows
                       if self._safe_float(next((trade.get("realized_r") for trade in closed if trade["trade_id"] == row["trade_id"]), 0)) < -.05]
        stop_distances = [row["stop_distance"] for row in stop_rows if row.get("stop_distance") is not None]
        lines = "\n".join(f"| {row['bucket']} | {row['n']} | {row['expectancy']} | {row['median_r']} | {row['profit_factor']} | {row['average_winner']} | {row['average_loser']} | {row['sample_label']} |"
                          for row in variant_summaries)
        markdown = f"""# Phase 2D.3 Trade Management Research

Generated: {datetime.now(timezone.utc).isoformat()}

Counterfactual research only. Canonical paper trades were not overwritten and live Free Validation behavior remains unchanged.

## Sample

- Closed natural trades replayed: {len(closed)}
- Actual canonical expectancy: {round(sum(actual_values)/len(actual_values), 4) if actual_values else 0}R
- Baseline replay expectancy: {baseline.get('expectancy')}
- Best replay variant by expectancy: {best.get('bucket')} at {best.get('expectancy')}R
- Baseline profit factor: {baseline.get('profit_factor')}
- Best replay profit factor: {best.get('profit_factor')}

## Variant results

| variant | N | expectancy | median R | profit factor | avg winner | avg loser | sample label |
|---|---:|---:|---:|---:|---:|---:|---|
{lines}

## MFE conditional analysis

- % reaching +0.25R: {threshold_rates['pct_reaching_0.25R']:.1%}
- % reaching +0.5R: {threshold_rates['pct_reaching_0.5R']:.1%}
- % reaching +0.75R: {threshold_rates['pct_reaching_0.75R']:.1%}
- % reaching +1R: {threshold_rates['pct_reaching_1.0R']:.1%}
- % reaching +1.5R: {threshold_rates['pct_reaching_1.5R']:.1%}
- % reaching +2R: {threshold_rates['pct_reaching_2.0R']:.1%}
- P(+1R reached | +0.5R reached): {conditional['p_1r_given_0_5r']:.1%}
- P(+1.5R reached | +1R reached): {conditional['p_1_5r_given_1r']:.1%}
- P(+2R reached | +1R reached): {conditional['p_2r_given_1r']:.1%}

## Stop efficiency

- Losing stop-outs that went positive first: {sum(1 for row in stop_rows if row['stopout'] and row['went_positive_first'])}
- Stop-outs that reached +0.5R before stopping: {sum(1 for row in stop_rows if row['reached_0_5r_before_stop'])}
- Stop-outs that reached +1R before stopping: {sum(1 for row in stop_rows if row['reached_1r_before_stop'])}
- Stop-outs reclaiming entry within 30m: {sum(1 for row in stop_rows if row['reclaimed_within_30m_after_stop'])}
- Average MAE of winners: {round(sum(winners_stop)/len(winners_stop), 4) if winners_stop else 0}
- Average MAE of losers: {round(sum(losers_stop)/len(losers_stop), 4) if losers_stop else 0}
- Median stop distance: {round(median(stop_distances), 4) if stop_distances else 0}
- Breakeven exit frequency: {be_exits}/{len(closed)}
- TP1-only exit frequency: {tp1_exits}/{len(closed)}

## Entry-edge summary

| horizon | N | avg forward return | avg MFE | avg MAE | P(+0.5R before -1R) | P(+1R before -1R) | P(+2R before -1R) |
|---|---:|---:|---:|---:|---:|---:|---:|
{entry_lines}

## Segment results excerpt

Full segmented output is in `trade_management_segment_summary.csv`.

| variant | segment | bucket | N | expectancy | profit factor | sample label |
|---|---|---|---:|---:|---:|---|
{segment_lines}

## Free Validation routing watch

This replay does not loosen gates or retro-convert Shadow trades. Current top setup-level Free Validation blockers remain:

| blocker | count |
|---|---:|
{routing_lines}

## Interpretation guardrail

Subgroups with N < 20 are labeled INSUFFICIENT_SAMPLE. No entry tuning, threshold tuning, target tuning, or production promotion should be made from tiny subgroup wins.

## Artifacts

- trade_management_replay.csv
- mfe_threshold_analysis.csv
- entry_edge_analysis.csv
- stop_efficiency_analysis.csv
- trade_management_segment_summary.csv
- counterfactual_exit_analysis.csv
"""
        markdown_path = self.output_root / "PHASE_2D3_TRADE_MANAGEMENT_RESEARCH.md"
        markdown_path.write_text(markdown, encoding="utf-8")
        return {"summary": {"closed_trades_replayed": len(closed), "canonical_expectancy": round(sum(actual_values)/len(actual_values), 4) if actual_values else 0,
                            "baseline_expectancy": baseline.get("expectancy"), "best_variant": best.get("bucket"),
                            "best_variant_expectancy": best.get("expectancy"), "baseline_profit_factor": baseline.get("profit_factor"),
                            "best_variant_profit_factor": best.get("profit_factor"),
                            "average_winner_baseline": baseline.get("average_winner"),
                            "average_winner_best_variant": best.get("average_winner"),
                            "be_exit_frequency": round(be_exits/len(closed), 4) if closed else 0,
                            "tp1_only_frequency": round(tp1_exits/len(closed), 4) if closed else 0,
                            "tp2_reach_frequency": threshold_rates.get("pct_reaching_1.5R", 0),
                            "tp3_reach_frequency": threshold_rates.get("pct_reaching_2.0R", 0),
                            **threshold_rates, **conditional},
                "variant_summaries": variant_summaries, "segment_summaries": segment_rows,
                "markdown_path": str(markdown_path),
                "csv_paths": [str(replay_path), str(mfe_path), str(entry_path), str(stop_path),
                              str(segment_path), str(counterfactual_path)]}


class ForwardManagementAB:
    """Forward paired A/B paper-management experiment.

    Branch records are research-only children of a canonical setup event. They do
    not create duplicate setup counts and do not alter the canonical paper broker.
    """

    BRANCHES = {
        "A": "TM_V0_CURRENT",
        "B": "TM_V3_TP1_PLUS_RUNNER",
    }

    def __init__(self, repository: Repository, settings: Any, watchlist: Any, output_root: Path):
        self.repository = repository
        self.settings = settings
        self.watchlist = watchlist
        self.output_root = output_root

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        return TradeManagementResearch._safe_float(value, default)

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        return TradeManagementResearch._parse_time(value)

    @staticmethod
    def _natural(payload: dict[str, Any]) -> bool:
        return TradeManagementResearch._natural(payload)

    def _spec(self, branch: dict[str, Any]) -> dict[str, Any]:
        targets = list(branch.get("targets") or [])
        tp1 = targets[0] if len(targets) > 0 else None
        tp3 = targets[2] if len(targets) > 2 else (targets[-1] if targets else None)
        if branch["management_version"] == "TM_V3_TP1_PLUS_RUNNER":
            return {"targets": [(tp1, .50, "TP1_PARTIAL"), (tp3, .50, "RUNNER_EXIT")],
                    "be_after": "TP1"}
        return {"targets": [(tp1, self._safe_float((self.settings.get("targets.partials", [.33]) or [.33])[0], .33),
                             "TP1_PARTIAL")],
                "be_after": "TP1"}

    def create_for_setup(self, setup: dict[str, Any] | Any) -> list[dict[str, Any]]:
        if hasattr(setup, "model_dump"):
            setup = setup.model_dump(mode="json")
        if not setup.get("trade_plan") or not self._natural(setup) or not str(setup.get("source_mode")).startswith("REAL_"):
            return []
        existing = self.repository.list_json("trade_management_branches", "WHERE parent_setup_id=?",
                                             (setup["setup_event_id"],), 10)
        if existing:
            return existing
        plan = setup["trade_plan"]
        rows = []
        created_at = setup.get("created_at_utc") or datetime.now(timezone.utc).isoformat()
        for branch, version in self.BRANCHES.items():
            row = {"branch_id": new_id("tmab"), "parent_setup_id": setup["setup_event_id"],
                   "branch": branch, "management_version": version, "ticker": setup["ticker"],
                   "setup_type": setup["setup_type"], "side": setup["side"], "status": "pending",
                   "created_at_utc": created_at,
                   "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                   "entry_zone_low": plan["entry_zone_low"], "entry_zone_high": plan["entry_zone_high"],
                   "entry": plan["planned_entry"], "stop_initial": plan["stop_initial"],
                   "stop_current": plan["stop_initial"], "tp_levels": plan["targets"],
                   "targets": plan["targets"], "initial_position_size": 1.0,
                   "remaining_size": 1.0, "realized_r": 0.0, "runner_contribution_r": 0.0,
                   "mfe_r": 0.0, "mae_r": 0.0, "bars_pending": 0,
                   "actual_fill_price": None, "opened_at_utc": None, "closed_at_utc": None,
                   "exit_reason": None, "events": [], "data_quality": (setup.get("score") or {}).get("data_quality_tier"),
                   "score_total": (setup.get("score") or {}).get("total"),
                   "score_bucket": TradeManagementResearch._score_bucket((setup.get("score") or {}).get("total"))}
            self.repository.store_trade_management_branch(row)
            rows.append(row)
        return rows

    def _event(self, branch: dict[str, Any], event_type: str, bar: dict[str, Any], price: float,
               fraction: float, realized: float, reason: str) -> None:
        branch["realized_r"] = round(self._safe_float(branch.get("realized_r")) + realized, 6)
        branch["remaining_size"] = round(max(0.0, self._safe_float(branch.get("remaining_size")) - fraction), 6)
        if event_type in {"RUNNER_EXIT", "TIME_EXIT"}:
            branch["runner_contribution_r"] = round(self._safe_float(branch.get("runner_contribution_r")) + realized, 6)
        branch.setdefault("events", []).append({
            "event_type": event_type, "timestamp": bar["bar_end_utc"], "execution_price": round(price, 6),
            "quantity_fraction": round(fraction, 6), "realized_r_event": round(realized, 6),
            "cumulative_r": branch["realized_r"], "remaining_size": branch["remaining_size"],
            "remaining_risk": 0 if abs(self._safe_float(branch.get("stop_current")) - self._safe_float(branch.get("actual_fill_price"))) <= .01
            else branch["remaining_size"], "reason": reason})

    def _duration_minutes(self, branch: dict[str, Any]) -> float | None:
        opened = self._parse_time(branch.get("opened_at_utc") or branch.get("created_at_utc"))
        closed = self._parse_time(branch.get("closed_at_utc"))
        return round((closed-opened).total_seconds()/60, 2) if opened and closed else None

    def _censor_after_rth_close(self) -> None:
        now = datetime.now(timezone.utc)
        rows = self.repository.list_json(
            "trade_management_branches", "WHERE status IN ('pending','open','partial')", (), 100000)
        for branch in rows:
            anchor = self._parse_time(branch.get("opened_at_utc") or branch.get("created_at_utc"))
            if not anchor:
                continue
            rth_close = TradeManagementResearch(self.repository, self.settings, self.watchlist, self.output_root)._rth_close(anchor)
            if now <= rth_close + timedelta(minutes=5):
                continue
            bars = self.repository.list_json("market_bars", "WHERE ticker=? AND timeframe=?",
                                             (branch["ticker"], "5m"), limit=100000)
            eligible = [bar for bar in bars if self._parse_time(bar.get("bar_end_utc"))
                        and self._parse_time(bar["bar_end_utc"]) <= rth_close]
            if not eligible:
                continue
            bar = sorted(eligible, key=lambda item: item["bar_end_utc"])[-1]
            if branch["status"] == "pending":
                branch["status"] = "censored"
                branch["closed_at_utc"] = bar["bar_end_utc"]
                branch["exit_reason"] = "rth_close_unfilled"
                branch.setdefault("events", []).append({
                    "event_type": "TIME_EXIT", "timestamp": bar["bar_end_utc"], "execution_price": None,
                    "quantity_fraction": 0.0, "realized_r_event": 0.0,
                    "cumulative_r": branch["realized_r"], "remaining_size": branch["remaining_size"],
                    "remaining_risk": 0, "reason": "rth_close_censor"})
            else:
                fill = self._safe_float(branch.get("actual_fill_price") or branch.get("entry"))
                stop = self._safe_float(branch.get("stop_initial"))
                risk = abs(fill - stop)
                side_mult = 1 if branch.get("side") == "LONG" else -1
                fraction = self._safe_float(branch.get("remaining_size"))
                price = self._safe_float(bar.get("close"))
                realized = (((price - fill) * side_mult) / risk * fraction) if risk else 0.0
                self._event(branch, "TIME_EXIT", bar, price, fraction, realized, "rth_close_censor")
                branch["status"] = "censored"
                branch["closed_at_utc"] = bar["bar_end_utc"]
                branch["exit_reason"] = "rth_close_censor"
            branch["duration_minutes"] = self._duration_minutes(branch)
            branch["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
            self.repository.store_trade_management_branch(branch)

    def update_for_bar(self, ticker: str, bar: dict[str, Any] | Any) -> list[dict[str, Any]]:
        if hasattr(bar, "model_dump"):
            bar = bar.model_dump(mode="json")
        rows = self.repository.list_json(
            "trade_management_branches", "WHERE ticker=? AND status IN ('pending','open','partial')",
            (ticker.upper(),), 1000)
        updates = []
        for branch in rows:
            created = self._parse_time(branch.get("created_at_utc"))
            bar_end = self._parse_time(bar.get("bar_end_utc"))
            if created and bar_end and created >= bar_end:
                continue
            if branch["status"] == "pending":
                branch["bars_pending"] = int(branch.get("bars_pending") or 0) + 1
                in_zone = self._safe_float(bar.get("low")) <= self._safe_float(branch.get("entry_zone_high")) and \
                    self._safe_float(bar.get("high")) >= self._safe_float(branch.get("entry_zone_low"))
                if in_zone:
                    branch["actual_fill_price"] = self._safe_float(branch.get("entry"))
                    branch["opened_at_utc"] = bar["bar_end_utc"]
                    branch["status"] = "open"
                    branch.setdefault("events", []).append({
                        "event_type": "ENTRY", "timestamp": bar["bar_end_utc"],
                        "execution_price": branch["actual_fill_price"], "quantity_fraction": 1.0,
                        "realized_r_event": 0.0, "cumulative_r": branch["realized_r"],
                        "remaining_size": branch["remaining_size"], "remaining_risk": branch["remaining_size"],
                        "reason": "paired_forward_branch_entry"})
                elif branch["bars_pending"] >= int(self.settings.get("execution.pending_order_expiry_bars", 3)):
                    branch["status"] = "censored"
                    branch["closed_at_utc"] = bar["bar_end_utc"]
                    branch["exit_reason"] = "pending_order_expiry"
                    branch["duration_minutes"] = self._duration_minutes(branch)
                    branch.setdefault("events", []).append({
                        "event_type": "TIME_EXIT", "timestamp": bar["bar_end_utc"],
                        "execution_price": None, "quantity_fraction": 0.0,
                        "realized_r_event": 0.0, "cumulative_r": branch["realized_r"],
                        "remaining_size": branch["remaining_size"], "remaining_risk": 0,
                        "reason": "censored_pending_order_expiry"})
                branch["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
                self.repository.store_trade_management_branch(branch)
                updates.append(branch)
                if branch["status"] != "open":
                    continue
            if branch["status"] not in {"open", "partial"}:
                continue
            fill = self._safe_float(branch.get("actual_fill_price") or branch.get("entry"))
            risk = abs(fill - self._safe_float(branch.get("stop_initial")))
            if risk <= 0:
                branch["status"] = "closed"
                branch["exit_reason"] = "invalid_risk"
                branch["closed_at_utc"] = bar["bar_end_utc"]
                self.repository.store_trade_management_branch(branch)
                continue
            side_mult = 1 if branch.get("side") == "LONG" else -1
            favorable = self._safe_float(bar.get("high")) - fill if side_mult == 1 else fill - self._safe_float(bar.get("low"))
            adverse = fill - self._safe_float(bar.get("low")) if side_mult == 1 else self._safe_float(bar.get("high")) - fill
            branch["mfe_r"] = round(max(self._safe_float(branch.get("mfe_r")), favorable / risk), 6)
            branch["mae_r"] = round(max(self._safe_float(branch.get("mae_r")), adverse / risk), 6)
            stop = self._safe_float(branch.get("stop_current"))
            stop_hit = self._safe_float(bar.get("low")) <= stop if side_mult == 1 else self._safe_float(bar.get("high")) >= stop
            if stop_hit:
                fraction = self._safe_float(branch.get("remaining_size"))
                realized = ((stop - fill) * side_mult / risk) * fraction
                event_type = "BREAKEVEN_EXIT" if abs(stop - fill) <= .01 else "STOP_EXIT"
                self._event(branch, event_type, bar, stop, fraction, realized, "paired_forward_stop")
                branch["status"] = "closed"
                branch["closed_at_utc"] = bar["bar_end_utc"]
                branch["exit_reason"] = "breakeven_stop" if event_type == "BREAKEVEN_EXIT" else "stop_loss"
                branch["duration_minutes"] = self._duration_minutes(branch)
                branch["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
                self.repository.store_trade_management_branch(branch)
                updates.append(branch)
                continue
            spec = self._spec(branch)
            already = {event["event_type"] for event in branch.get("events", [])}
            for price, fraction, event_type in spec["targets"]:
                if price is None or event_type in already or self._safe_float(branch.get("remaining_size")) <= 0:
                    continue
                hit = self._safe_float(bar.get("high")) >= self._safe_float(price) if side_mult == 1 else \
                    self._safe_float(bar.get("low")) <= self._safe_float(price)
                if not hit:
                    continue
                close_fraction = min(self._safe_float(branch.get("remaining_size")), fraction)
                realized = ((self._safe_float(price) - fill) * side_mult / risk) * close_fraction
                self._event(branch, event_type, bar, self._safe_float(price), close_fraction, realized,
                            branch["management_version"])
                if spec["be_after"] == "TP1" and event_type == "TP1_PARTIAL":
                    branch["stop_current"] = fill
                    branch.setdefault("events", []).append({
                        "event_type": "STOP_MOVE", "timestamp": bar["bar_end_utc"], "execution_price": fill,
                        "quantity_fraction": 0.0, "realized_r_event": 0.0,
                        "cumulative_r": branch["realized_r"], "remaining_size": branch["remaining_size"],
                        "remaining_risk": 0, "reason": f"{branch['management_version']} breakeven rule"})
                if self._safe_float(branch.get("remaining_size")) <= 0:
                    branch["status"] = "closed"
                    branch["closed_at_utc"] = bar["bar_end_utc"]
                    branch["exit_reason"] = "runner_exit" if event_type == "RUNNER_EXIT" else event_type.lower()
                    branch["duration_minutes"] = self._duration_minutes(branch)
                    break
                branch["status"] = "partial"
                already.add(event_type)
            branch["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
            self.repository.store_trade_management_branch(branch)
            updates.append(branch)
        return updates

    def status(self) -> dict[str, Any]:
        self._censor_after_rth_close()
        rows = self.repository.list_json("trade_management_branches", limit=100000)
        completed = [row for row in rows if row.get("status") in {"closed", "censored"}]
        by_branch: dict[str, list[dict[str, Any]]] = {}
        for row in completed:
            by_branch.setdefault(row["branch"], []).append(row)

        def summary(branch: str) -> dict[str, Any]:
            items = by_branch.get(branch, [])
            values = [self._safe_float(row.get("realized_r")) for row in items]
            wins = [value for value in values if value > .05]
            losses = [value for value in values if value < -.05]
            equity = peak = max_dd = 0.0
            for value in values:
                equity += value
                peak = max(peak, equity)
                max_dd = max(max_dd, peak-equity)
            return {"branch": branch, "management_version": self.BRANCHES[branch], "n": len(items),
                    "expectancy": round(sum(values)/len(values), 4) if values else 0,
                    "median_r": round(median(values), 4) if values else 0,
                    "profit_factor": round(sum(wins)/abs(sum(losses)), 4) if losses else (None if not wins else "infinite"),
                    "win_rate": round(len(wins)/len(values), 4) if values else 0,
                    "average_winner": round(sum(wins)/len(wins), 4) if wins else 0,
                    "average_loser": round(sum(losses)/len(losses), 4) if losses else 0,
                    "max_drawdown": round(max_dd, 4),
                    "tp1_frequency": round(sum(any(event["event_type"] == "TP1_PARTIAL" for event in row.get("events", []))
                                               for row in items)/len(items), 4) if items else 0,
                    "runner_contribution": round(sum(self._safe_float(row.get("runner_contribution_r")) for row in items), 4),
                    "be_frequency": round(sum(row.get("exit_reason") == "breakeven_stop" for row in items)/len(items), 4)
                    if items else 0}

        parent_counts = Counter(row["parent_setup_id"] for row in rows)
        paired = [parent for parent, count in parent_counts.items() if count == 2]
        completed_parent_counts = Counter(row["parent_setup_id"] for row in completed)
        completed_paired = [parent for parent, count in completed_parent_counts.items() if count == 2]
        result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                  "experiment_label": "COUNTERFACTUAL_FORWARD_AB_RESEARCH",
                  "acceptance_target": 100,
                  "parent_setups": len(parent_counts),
                  "paired_parent_setups": len(paired),
                  "paired_completed_or_censored": len(completed_paired),
                  "remaining_to_target": max(0, 100-len(completed_paired)),
                  "branches": [summary("A"), summary("B")],
                  "open_branches": sum(row.get("status") in {"pending", "open", "partial"} for row in rows),
                  "decision_rule": {
                      "eligible_to_consider_promotion": len(completed_paired) >= 100,
                      "requires_positive_expectancy_improvement": True,
                      "requires_pf_improvement": True,
                      "requires_drawdown_not_materially_worse": True,
                      "requires_not_symbol_concentrated": True,
                  }}
        branch_by = {row["branch"]: row for row in result["branches"]}
        if branch_by.get("A") and branch_by.get("B"):
            result["expectancy_delta_b_minus_a"] = round(
                branch_by["B"]["expectancy"] - branch_by["A"]["expectancy"], 4)
            result["profit_factor_delta_b_minus_a"] = (
                None if branch_by["A"]["profit_factor"] in {None, "infinite"} or
                branch_by["B"]["profit_factor"] in {None, "infinite"} else
                round(branch_by["B"]["profit_factor"] - branch_by["A"]["profit_factor"], 4))
        return result

    def generate_report(self) -> dict[str, Any]:
        self._censor_after_rth_close()
        rows = self.repository.list_json("trade_management_branches", limit=100000)
        status = self.status()
        path = self.output_root / "PHASE_2D4_FORWARD_MANAGEMENT_AB.md"
        csv_path = self.output_root / "forward_management_ab_branches.csv"
        branch_rows = []
        for row in rows:
            events = row.get("events", [])
            branch_rows.append({
                "parent_setup_id": row["parent_setup_id"], "branch": row["branch"],
                "management_version": row["management_version"], "ticker": row["ticker"],
                "setup_type": row.get("setup_type"), "direction": row.get("side"),
                "status": row["status"], "entry": row.get("actual_fill_price") or row.get("entry"),
                "stop": row.get("stop_initial"), "tp_levels": row.get("tp_levels"),
                "partial_events": [event for event in events if "PARTIAL" in event.get("event_type", "")],
                "runner_events": [event for event in events if event.get("event_type") in {"RUNNER_EXIT", "TIME_EXIT"}],
                "all_events": events, "realized_r": row.get("realized_r"),
                "mfe": row.get("mfe_r"), "mae": row.get("mae_r"),
                "duration_minutes": row.get("duration_minutes") or self._duration_minutes(row),
                "exit_reason": row.get("exit_reason")})
        pd.DataFrame(branch_rows).map(lambda value: json.dumps(value, sort_keys=True, default=str)
                                     if isinstance(value, (list, dict, tuple)) else value).to_csv(csv_path, index=False)
        branch_lines = "\n".join(
            f"| {row['branch']} | {row['management_version']} | {row['n']} | {row['expectancy']} | {row['median_r']} | {row['profit_factor']} | {row['win_rate']:.1%} | {row['average_winner']} | {row['average_loser']} | {row['max_drawdown']} | {row['tp1_frequency']:.1%} | {row['runner_contribution']} | {row['be_frequency']:.1%} |"
            for row in status["branches"])
        markdown = f"""# Phase 2D.4 Forward Management A/B

Generated: {status['generated_at_utc']}

Forward paired paper-management experiment. One natural setup event creates two research branches only:

- Branch A: TM_V0_CURRENT
- Branch B: TM_V3_TP1_PLUS_RUNNER

Canonical paper trades, entry logic, score weights, thresholds, GEX logic, macro guard, stop construction, provider gates, live-trading structure, and Portfolio OS isolation remain unchanged.

## Progress

- Paired parent setups: {status['paired_parent_setups']}
- Paired completed or censored: {status['paired_completed_or_censored']} / 100
- Remaining to acceptance target: {status['remaining_to_target']}
- Open research branches: {status['open_branches']}

## A/B comparison

| branch | version | N | expectancy | median R | profit factor | win rate | avg winner | avg loser | max drawdown | TP1 freq | runner contribution | BE freq |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{branch_lines}

## Decision rule

TM_V3_TP1_PLUS_RUNNER is not eligible for promotion until N >= 100 paired setups and Branch B keeps positive expectancy improvement, improves profit factor, does not materially worsen drawdown, and is not driven by one or two symbols.

Current promotion-eligible: {status['decision_rule']['eligible_to_consider_promotion']}
"""
        path.write_text(markdown, encoding="utf-8")
        return {"status": status, "markdown_path": str(path), "csv_paths": [str(csv_path)]}


class DailyObservationReporter:
    def __init__(self, repository: Repository, reports_root: Path):
        self.repository = repository
        self.reports_root = reports_root

    @staticmethod
    def _average(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0

    def generate(self, report_date: str | None = None) -> dict[str, Any]:
        eastern = ZoneInfo("America/New_York")
        report_date = report_date or datetime.now(eastern).date().isoformat()
        local_day = datetime.fromisoformat(report_date).date()
        start_at = datetime.combine(local_day, time.min, eastern).astimezone(timezone.utc)
        end_at = start_at + timedelta(days=1)
        start, end = start_at.isoformat(), end_at.isoformat()
        observations = self.repository.list_json("scan_observations",
                                                  "WHERE observed_at_utc>=? AND observed_at_utc<?", (start, end), 100000)
        trades = self.repository.list_json("paper_trades",
                                            "WHERE created_at_utc>=? AND created_at_utc<?", (start, end), 100000)
        failures = self.repository.list_json("provider_failures",
                                              "WHERE occurred_at_utc>=? AND occurred_at_utc<?", (start, end), 100000)
        ablations = self.repository.list_json("real_ablation_results",
                                               "WHERE created_at_utc>=? AND created_at_utc<?", (start, end), 100000)
        scans_by_ticker: dict[str, int] = {}
        for item in observations:
            scans_by_ticker[item["ticker"]] = scans_by_ticker.get(item["ticker"], 0) + 1
        outcomes: dict[str, int] = {}
        for item in observations:
            outcomes[item["outcome"]] = outcomes.get(item["outcome"], 0) + 1
        production = [item for item in trades if item["mode"] == "production_paper"]
        free_validation = [item for item in trades if item["mode"] == "free_validation_paper"]
        shadow = [item for item in trades if item["mode"] == "shadow_paper"]
        valid_real = [item for item in observations if item.get("production_eligible")]
        valid_free = [item for item in observations if item.get("free_validation_eligible")]
        shadow_observations = [item for item in observations if item.get("lane") == "shadow_paper" or
                               (not item.get("free_validation_eligible") and not item.get("production_eligible"))]
        rejected = [item for item in observations if item["outcome"] in {"rejected", "provider_error"}]
        shadow_only = [item for item in observations if item["outcome"] == "shadow_paper"]
        stale_incomplete = [item for item in observations if any(token in " ".join(item.get("reasons", [])).lower()
                            for token in ("stale", "freshness", "incomplete", "missing", "bid", "ask"))]
        macro_blocks = [item for item in observations if any("event window" in reason.lower()
                        for reason in item.get("reasons", []))]
        missing_oi_greeks = [item for item in observations if
            item.get("data_quality", {}).get("oi_unavailable") or
            item.get("data_quality", {}).get("greeks_unavailable") or any(
                str(reason).lower() in {"open_interest", "greeks"} for reason in item.get("reasons", []))]
        scores = [float(item["score_total"]) for item in observations if item.get("score_total") is not None]
        score_distribution = {"0-49": 0, "50-59": 0, "60-74": 0, "75-84": 0, "85-100": 0}
        for score in scores:
            bucket = "0-49" if score < 50 else "50-59" if score < 60 else "60-74" if score < 75 else "75-84" if score < 85 else "85-100"
            score_distribution[bucket] += 1
        closed = [item for item in trades if item["status"] == "closed"]
        ticker_r: dict[str, list[float]] = {}
        for item in closed:
            ticker_r.setdefault(item["ticker"], []).append(float(item.get("realized_r", 0)))
        ticker_expectancy = {ticker: self._average(values) for ticker, values in ticker_r.items()}
        best = max(ticker_expectancy, key=ticker_expectancy.get) if ticker_expectancy else None
        worst = min(ticker_expectancy, key=ticker_expectancy.get) if ticker_expectancy else None
        time_to_tp, time_to_exit = [], []
        for item in closed:
            opened = datetime.fromisoformat(item["opened_at_utc"].replace("Z", "+00:00")) if item.get("opened_at_utc") else None
            tp1 = datetime.fromisoformat(item["tp1_at_utc"].replace("Z", "+00:00")) if item.get("tp1_at_utc") else None
            closed_at = datetime.fromisoformat(item["closed_at_utc"].replace("Z", "+00:00")) if item.get("closed_at_utc") else None
            if opened and tp1:
                time_to_tp.append((tp1-opened).total_seconds()/60)
            if opened and closed_at:
                time_to_exit.append((closed_at-opened).total_seconds()/60)
        model_scores: dict[str, list[float]] = {}
        variant_counts: dict[str, int] = {}
        for item in ablations:
            if item.get("score_total") is not None:
                model_scores.setdefault(item["model_name"], []).append(float(item["score_total"]))
            if item.get("variant_type"):
                key = f"{item['variant_type']}:{item.get('variant_value')}"
                variant_counts[key] = variant_counts.get(key, 0) + 1
        setup_r: dict[str, list[float]] = {}
        for item in closed:
            setup_r.setdefault(item["setup_type"], []).append(float(item.get("realized_r", 0)))
        setup_expectancy = {name: self._average(values) for name, values in setup_r.items()}
        best_setup = max(setup_expectancy, key=setup_expectancy.get) if setup_expectancy else None
        worst_setup = min(setup_expectancy, key=setup_expectancy.get) if setup_expectancy else None
        report = {
            "report_date_et": report_date, "report_date_utc": report_date,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_scans": len(observations), "scans_by_ticker": scans_by_ticker, "scan_outcomes": outcomes,
            "valid_real_scans": len(valid_real),
            "valid_free_validation_scans": len(valid_free), "shadow_scans": len(shadow_observations),
            "production_paper_trades": len(production), "free_validation_paper_trades": len(free_validation),
            "shadow_paper_trades": len(shadow),
            "trades_opened": len(trades), "trades_closed": len(closed),
            "rejected_scans": len(rejected), "stale_incomplete_cases": len(stale_incomplete),
            "rejected_scan_events": rejected, "shadow_only_events": shadow_only,
            "macro_guard_blocks": len(macro_blocks), "missing_oi_greeks_count": len(missing_oi_greeks),
            "average_score": self._average(scores),
            "score_distribution": score_distribution,
            "closed_trade_results": {"sample_size": len(closed),
                "average_R": self._average([float(item.get("realized_r", 0)) for item in closed]),
                "median_MFE_R": round(median([float(item.get("mfe_r", 0)) for item in closed]), 4) if closed else 0,
                "median_MAE_R": round(median([float(item.get("mae_r", 0)) for item in closed]), 4) if closed else 0,
                "average_time_to_TP1_minutes": self._average(time_to_tp),
                "average_time_to_exit_minutes": self._average(time_to_exit),
                "best_ticker": best, "worst_ticker": worst, "ticker_expectancy_R": ticker_expectancy,
                "best_setup": best_setup, "worst_setup": worst_setup,
                "setup_expectancy_R": setup_expectancy},
            "provider_failures": {"count": len(failures), "events": failures},
            "real_data_ablation": {"model_average_scores": {name: self._average(values) for name, values in model_scores.items()},
                                   "variant_counts": variant_counts, "optimization_performed": False,
                                   "note": "Collection only; no production weights or parameters changed."},
        }
        output_dir = self.reports_root / report_date
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path, markdown_path = output_dir / "daily_report.json", output_dir / "daily_report.md"
        json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        trades_path, scans_path = output_dir / "trades.csv", output_dir / "scans.csv"
        ablation_path = output_dir / "ablation_summary.csv"
        pd.json_normalize(trades).to_csv(trades_path, index=False)
        # Keep the operational CSV compact.  The full normalized payload remains
        # in SQLite; exporting nested bars/provider payloads caused each daily
        # report to grow by hundreds of megabytes without adding report value.
        scan_export = []
        for item in observations:
            scan_export.append({
                "observation_id": item.get("observation_id"),
                "run_id": item.get("run_id"),
                "ticker": item.get("ticker"),
                "observed_at_utc": item.get("observed_at_utc"),
                "candle_end_utc": item.get("candle_end_utc"),
                "data_mode": item.get("data_mode"),
                "outcome": item.get("outcome"),
                "lane": item.get("lane"),
                "free_validation_eligible": item.get("free_validation_eligible"),
                "production_eligible": item.get("production_eligible"),
                "setup_event_id": item.get("setup_event_id"),
                "score_total": item.get("score_total"),
                "reasons": json.dumps(item.get("reasons") or [], sort_keys=True, default=str),
                "providers": json.dumps(item.get("providers") or {}, sort_keys=True, default=str),
                "data_quality": json.dumps(item.get("data_quality") or {}, sort_keys=True, default=str),
            })
        pd.DataFrame(scan_export).to_csv(scans_path, index=False)
        ablation_rows = [
            {"model_or_variant": name, "kind": "score_model", "observations": len(values),
             "average_score": self._average(values)} for name, values in sorted(model_scores.items())]
        ablation_rows.extend(
            {"model_or_variant": name, "kind": "variant", "observations": count,
             "average_score": None} for name, count in sorted(variant_counts.items()))
        pd.DataFrame(ablation_rows, columns=["model_or_variant", "kind", "observations", "average_score"]).to_csv(
            ablation_path, index=False)
        ticker_rows = "\n".join(f"| {ticker} | {count} |" for ticker, count in sorted(scans_by_ticker.items())) or "| — | 0 |"
        markdown = f"""# Options Structure Trader Daily Report — {report_date}

This is a data-quality and observation report. No parameters were optimized.

## Scan summary

| Ticker | Scans |
|---|---:|
{ticker_rows}

- Total scans: {report['total_scans']}
- Free Validation-valid scans: {report['valid_free_validation_scans']}
- Shadow observations: {report['shadow_scans']}
- Production-valid real scans: {report['valid_real_scans']}
- Free Validation Paper trades: {report['free_validation_paper_trades']}
- Production Paper trades: {report['production_paper_trades']}
- Shadow Paper trades: {report['shadow_paper_trades']}
- Rejected scans: {report['rejected_scans']}
- Stale/incomplete cases: {report['stale_incomplete_cases']}
- Macro-guard blocks: {report['macro_guard_blocks']}
- Missing OI/Greeks cases: {report['missing_oi_greeks_count']}
- Average score: {report['average_score']}
- Score distribution: {json.dumps(score_distribution, sort_keys=True)}

## Results

- Closed trades: {len(closed)}
- Trades opened/closed: {len(trades)} / {len(closed)}
- Average R: {report['closed_trade_results']['average_R']}
- Median MFE/MAE: {report['closed_trade_results']['median_MFE_R']}R / {report['closed_trade_results']['median_MAE_R']}R
- Average time to TP1/exit: {report['closed_trade_results']['average_time_to_TP1_minutes']} / {report['closed_trade_results']['average_time_to_exit_minutes']} minutes
- Best/worst ticker: {best or 'N/A'} / {worst or 'N/A'}
- Best/worst setup: {best_setup or 'N/A'} / {worst_setup or 'N/A'}

## Data providers

- Provider failures: {len(failures)}
- Real-data ablation observations: {len(ablations)}
- Optimization performed: **No**
"""
        markdown_path.write_text(markdown, encoding="utf-8")
        self.repository.store_daily_report(report_date, str(markdown_path), report)
        return {"report": report, "json_path": str(json_path), "markdown_path": str(markdown_path),
                "trades_csv_path": str(trades_path), "scans_csv_path": str(scans_path),
                "ablation_summary_csv_path": str(ablation_path)}


class FreeValidationAcceptanceReporter:
    """Builds the Phase 2C evidence report without treating repeated candle polls as new scans."""

    def __init__(self, repository: Repository, output_path: Path):
        self.repository = repository
        self.output_path = output_path

    def generate(self, provider_status: list[dict[str, Any]], macro_approved: bool,
                 target: int = 50) -> dict[str, Any]:
        observations = self.repository.list_json("scan_observations", limit=100000)
        trades = self.repository.list_json("paper_trades", limit=100000)
        failures = self.repository.list_json("provider_failures", limit=100000)
        unique_free: dict[tuple[str, str], dict[str, Any]] = {}
        for row in observations:
            if row.get("free_validation_eligible") and row.get("candle_end_utc"):
                unique_free[(row["ticker"], row["candle_end_utc"])] = row
        free_rows = list(unique_free.values())
        shadow = [row for row in observations if row.get("lane") == Mode.SHADOW.value or
                  (not row.get("free_validation_eligible") and not row.get("production_eligible"))]
        rejected = [row for row in observations if row.get("outcome") in {"rejected", "provider_error"}]
        reasons = Counter(reason for row in observations for reason in row.get("reasons", []))
        missing = Counter(component for row in observations
                          for component in row.get("data_quality", {}).get("missing_components", []))
        scans_by_ticker = Counter(row["ticker"] for row in free_rows)
        stale = [row for row in observations if any(
            token in str(reason).lower() for reason in row.get("reasons", [])
            for token in ("stale", "freshness", "incomplete"))]
        macro_blocks = [row for row in observations if any(
            "event" in str(reason).lower() and "block" in str(reason).lower()
            for reason in row.get("reasons", []))]
        scores = [float(row["score_total"]) for row in free_rows if row.get("score_total") is not None]
        score_buckets = Counter("0-49" if score < 50 else "50-59" if score < 60 else
                                "60-74" if score < 75 else "75-84" if score < 85 else "85-100"
                                for score in scores)
        valid_no_trade = [row for row in free_rows if not row.get("setup_event_id")]
        detailed = next((row for row in free_rows if row.get("payload", {}).get("scan")), None)
        free_trades = [row for row in trades if row.get("mode") == Mode.FREE_VALIDATION.value]
        synthetic_free = [row for row in free_trades if "synthetic" in json.dumps(row).lower()]
        configured = [item["name"] for item in provider_status if item.get("configured") and item.get("enabled")]
        missing_providers = [item["name"] for item in provider_status if not item.get("configured")]
        production_blockers = {reason for row in observations for reason in row.get("reasons", [])
                               if "Production" in reason or "production" in reason}
        if not macro_approved:
            production_blockers.add("Manual macro calendar is not approved")
        if not any(item.get("configured") and item.get("production_eligible") and
                   "ohlcv" in " ".join(item.get("capabilities", [])).lower() for item in provider_status):
            production_blockers.add("No configured Production-eligible candle provider")
        if not any(item.get("configured") and item.get("production_eligible") and
                   any(token in " ".join(item.get("capabilities", [])).lower()
                       for token in ("gex", "chain", "greeks")) for item in provider_status):
            production_blockers.add("No configured complete Production-eligible options-structure provider")
        production_blockers = sorted(production_blockers)
        accepted = len(free_rows) >= target and not synthetic_free
        result = {
            "status": "PASSED" if accepted else "EMPIRICAL_ACCEPTANCE_PENDING",
            "target": target, "free_validation_valid_scans": len(free_rows),
            "free_validation_trades": len(free_trades), "synthetic_free_validation_trades": len(synthetic_free),
            "shadow_scans": len(shadow), "rejected_scans": len(rejected),
            "stale_incomplete_count": len(stale), "macro_guard_blocks": len(macro_blocks),
            "scans_by_ticker": dict(sorted(scans_by_ticker.items())),
            "reason_distribution": dict(reasons.most_common()),
            "missing_component_distribution": dict(missing.most_common()),
            "average_score": round(sum(scores) / len(scores), 3) if scores else None,
            "score_distribution": dict(score_buckets), "provider_failures": failures,
            "configured_providers": configured, "missing_providers": missing_providers,
            "macro_calendar_approved": macro_approved, "production_blockers": production_blockers,
            "valid_no_trade_examples": valid_no_trade[:3], "rejected_examples": rejected[:3],
            "detailed_scan": detailed,
        }
        provider_lines = "\n".join(
            f"- {item['name']}: {'ready' if item.get('configured') else 'not configured'}; "
            f"Free Validation={'yes' if item.get('free_validation_eligible') else 'no'}; "
            f"Production={'yes' if item.get('production_eligible') else 'no'}"
            for item in provider_status
        ) or "- No adapters reported"
        ticker_lines = "\n".join(f"| {ticker} | {count} |" for ticker, count in sorted(scans_by_ticker.items())) or "| — | 0 |"
        reason_lines = "\n".join(f"- {name}: {count}" for name, count in reasons.most_common(15)) or "- None"
        missing_lines = "\n".join(f"- {name}: {count}" for name, count in missing.most_common()) or "- None"
        no_trade_lines = "\n".join(
            f"- {row['ticker']} at {row.get('candle_end_utc')}: valid data, but no post-level reclaim candle."
            for row in valid_no_trade[:3]) or "- No Free-Validation-valid no-trade scan has been collected yet."
        rejected_lines = "\n".join(
            f"- {row['ticker']}: {', '.join(row.get('reasons', [])[:4])}"
            for row in rejected[:3]) or "- No rejected example has been recorded yet."
        if detailed:
            scan = detailed.get("payload", {}).get("scan", {})
            level = scan.get("level", {})
            bar = scan.get("confirmation_bar", {})
            lifecycle = (f"- Observation: `{detailed['observation_id']}`\n- Ticker/candle: {detailed['ticker']} / "
                         f"{detailed.get('candle_end_utc')}\n- Level: {level.get('level_type')} at {level.get('price')}\n"
                         f"- Confirmation close: {bar.get('close')}\n- Outcome: {detailed.get('outcome')}\n"
                         f"- Lane: {detailed.get('lane')}\n- Result: "
                         f"{'paper lifecycle stored' if detailed.get('setup_event_id') else 'no reclaim setup; no trade opened'}")
        else:
            lifecycle = "- Pending: no Free-Validation-valid detailed scan exists yet."
        blockers = "\n".join(f"- {item}" for item in production_blockers) or "- No Production blocker captured yet."
        markdown = f"""# Phase 2C Free Validation Report

Generated: {datetime.now(timezone.utc).isoformat()}

**Acceptance status: {result['status']}**

The empirical gate requires {target} unique, completed-candle Free Validation scans during US RTH. Current progress is **{len(free_rows)}/{target}**. Repeated polls of the same ticker/candle count once.

## Provider status

{provider_lines}

- Macro calendar approved: {macro_approved}
- Provider failures: {len(failures)}

## Lane totals

- Free Validation valid scans: {len(free_rows)}
- Free Validation trades: {len(free_trades)}
- Synthetic trades in Free Validation: {len(synthetic_free)}
- Shadow observations: {len(shadow)}
- Rejected observations: {len(rejected)}
- Stale/incomplete observations: {len(stale)}
- Macro guard blocks: {len(macro_blocks)}

## Scans by ticker

| Ticker | Unique valid scans |
|---|---:|
{ticker_lines}

## Score and missing-data distribution

- Average score: {result['average_score'] if result['average_score'] is not None else 'N/A'}
- Score distribution: {json.dumps(dict(score_buckets), sort_keys=True)}

{missing_lines}

## Reason distribution

{reason_lines}

## Valid but no-trade examples

{no_trade_lines}

## Rejected examples

{rejected_lines}

## Detailed scan lifecycle

{lifecycle}

## Current blockers for Production Paper

{blockers}

## Safety and interpretation

- Live trading remains structurally disabled.
- Free Validation is limited-data research paper trading and cannot be promoted to real execution.
- Production Paper gates remain unchanged and strict.
- No score weights, thresholds, stops, targets, or sizing parameters were optimized.
"""
        self.output_path.write_text(markdown, encoding="utf-8")
        return {"report": result, "markdown_path": str(self.output_path)}


class DaemonWatchlistReporter:
    def __init__(self, repository: Repository, output_path: Path):
        self.repository, self.output_path = repository, output_path

    def generate(self, watchlist: Any, scheduler_status: dict[str, Any],
                 provider_status: list[dict[str, Any]], targets: dict[str, int]) -> dict[str, Any]:
        rows = self.repository.list_json("scan_observations", limit=100000)
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            if row.get("free_validation_eligible") and row.get("candle_end_utc"):
                unique[(row["ticker"], row["candle_end_utc"])] = row
        valid = list(unique.values())
        valid_symbols = sorted({row["ticker"] for row in valid})
        tier1 = {entry.symbol for entry in watchlist.entries.values() if entry.tier == "tier_1_core"}
        tier1_scans = len([row for row in valid if row["ticker"] in tier1])
        synthetic = [row for row in valid if "synthetic" in json.dumps(row).lower()]
        configured = len(watchlist.entries)
        acceptance = (len(valid) >= targets["total"] and tier1_scans >= targets["tier1"] and
                      len(valid_symbols) >= targets["symbols"] and not synthetic)
        result = {"status": "PASSED" if acceptance else "EMPIRICAL_ACCEPTANCE_PENDING",
                  "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                  "free_validation_scans": len(valid), "target_free_validation_scans": targets["total"],
                  "tier1_scans": tier1_scans, "target_tier1_scans": targets["tier1"],
                  "valid_symbols": len(valid_symbols), "target_valid_symbols": targets["symbols"],
                  "valid_symbol_names": valid_symbols, "configured_watchlist_symbols": configured,
                  "synthetic_free_validation_scans": len(synthetic), "scheduler": scheduler_status,
                  "providers": provider_status, "live_trading_disabled": True,
                  "external_portfolio_integration": False}
        markdown = f"""# Phase 2D Daemon and Watchlist Report

Generated: {result['generated_at_utc']}

**Acceptance status: {result['status']}**

## Empirical progress

- Free Validation scans: **{len(valid)}/{targets['total']}**
- Tier 1 Free Validation scans: **{tier1_scans}/{targets['tier1']}**
- Symbols with valid scans: **{len(valid_symbols)}/{targets['symbols']}**
- Synthetic Free Validation scans: **{len(synthetic)}**
- Configured watchlist symbols: **{configured}**

## Daemon

- Status: {scheduler_status.get('daemon_status', 'NOT_STARTED')}
- Current session state: {scheduler_status.get('current_session_state', 'unknown')}
- Next RTH open: {scheduler_status.get('next_rth_open')}
- Next RTH close: {scheduler_status.get('next_rth_close')}
- Last scan: {scheduler_status.get('last_scan_time')}
- Next scan: {scheduler_status.get('next_scan_time')}
- Daily report status: {scheduler_status.get('daily_report_status', 'pending')}
- Last error: {scheduler_status.get('last_error') or 'None'}

## Provider readiness

""" + "\n".join(
            f"- {item['name']}: {'configured' if item.get('configured') else 'not configured'}; "
            f"Free Validation={'yes' if item.get('free_validation_eligible') else 'no'}"
            for item in provider_status) + """

## Safety

- Live trading remains structurally disabled.
- No broker order submission route exists.
- The daemon uses this project's standalone database, broker, journal, logs, and reports.
- No Portfolio OS integration or writes are present.
- No score, setup, stop, target, sizing, or Production eligibility logic was changed.

The empirical gate remains pending until all scan-count and symbol-coverage targets are met naturally during valid RTH windows.
"""
        self.output_path.write_text(markdown, encoding="utf-8")
        return {"report": result, "markdown_path": str(self.output_path)}
