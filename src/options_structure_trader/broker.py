from __future__ import annotations

from .config import Settings
from .db import Repository
from .models import Bar, Mode, PaperTrade, SetupEvent, Side


class StandalonePaperBroker:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository

    def accept(self, setup: SetupEvent, mode: Mode | None = None, variant_id: str | None = None) -> PaperTrade:
        if not setup.trade_plan:
            raise ValueError("Setup has no valid trade plan")
        mode = mode or setup.recommended_mode
        if mode == Mode.PRODUCTION and not setup.production_paper_allowed:
            raise ValueError("Blocked setup cannot enter Production Paper")
        if mode == Mode.FREE_VALIDATION and not setup.free_validation_paper_allowed:
            raise ValueError("Blocked setup cannot enter Free Validation Paper")
        if mode not in {Mode.PRODUCTION, Mode.FREE_VALIDATION, Mode.SHADOW}:
            raise ValueError("Only standalone paper modes are executable")
        if mode in {Mode.PRODUCTION, Mode.FREE_VALIDATION}:
            open_trades = self.repository.list_json("paper_trades", "WHERE mode=? AND status IN ('pending','open','partial')", (mode.value,))
            if len(open_trades) >= self.settings.get("risk.max_open_positions", 3):
                raise ValueError("Maximum open positions reached")
            if any(item["ticker"] == setup.ticker for item in open_trades):
                raise ValueError("Maximum same-ticker positions reached")
        plan = setup.trade_plan
        trade = PaperTrade(setup_event_id=setup.setup_event_id, ticker=setup.ticker,
                           setup_type=setup.setup_type.value, side=setup.side, mode=mode,
                           entry_zone_low=plan.entry_zone_low, entry_zone_high=plan.entry_zone_high,
                           planned_entry=plan.planned_entry, stop_initial=plan.stop_initial,
                           stop_current=plan.stop_initial, targets=plan.targets, shares=plan.shares,
                           remaining_shares=plan.shares, risk_dollars=plan.risk_dollars,
                           score_total=setup.score.total, score_breakdown=setup.score.breakdown,
                           score_model_version=setup.score.score_model_version,
                           config_version=setup.config_version,
                           macro_event_flags={
                               "blocked": bool((setup.signal_snapshot.get("guard") or {}).get("blocked")),
                               "macro_event_proximity_flag": bool((setup.signal_snapshot.get("guard") or {}).get("macro_event_proximity_flag")),
                               "event_name": (setup.signal_snapshot.get("guard") or {}).get("event_name"),
                               "macro_unknown": bool((setup.signal_snapshot.get("guard") or {}).get("macro_unknown")),
                               "limited_data": bool((setup.signal_snapshot.get("eligibility") or {}).get("limited_data")),
                               "unofficial_source": bool((setup.signal_snapshot.get("eligibility") or {}).get("unofficial_source")),
                               "production_grade": bool((setup.signal_snapshot.get("eligibility") or {}).get("production_grade")),
                           },
                           variant_id=variant_id)
        self.repository.store_trade(trade)
        return trade

    def on_bar(self, trade: PaperTrade, bar: Bar, liquidity_bucket: str = "medium") -> PaperTrade:
        if trade.status == "pending":
            trade.bars_pending += 1
            in_zone = bar.low <= trade.entry_zone_high and bar.high >= trade.entry_zone_low
            if in_zone:
                bps = self.settings.get(f"execution.slippage_bps.{liquidity_bucket}", 3.0)
                adverse = trade.planned_entry * bps / 10_000
                trade.actual_fill_price = trade.planned_entry + adverse if trade.side == Side.LONG else trade.planned_entry - adverse
                trade.slippage = adverse * trade.shares
                trade.status = "open"
                trade.opened_at_utc = bar.bar_end_utc
            elif trade.bars_pending >= self.settings.get("execution.pending_order_expiry_bars", 3):
                trade.status, trade.exit_reason = "expired", "pending_order_expiry"
                trade.closed_at_utc = bar.bar_end_utc
            self.repository.store_trade(trade)
            if trade.status != "open":
                return trade
        if trade.status not in {"open", "partial"} or trade.actual_fill_price is None:
            return trade
        fill = trade.actual_fill_price
        risk_per_share = abs(fill - trade.stop_initial)
        if risk_per_share <= 0:
            trade.status, trade.exit_reason = "closed", "invalid_risk"
            trade.closed_at_utc = bar.bar_end_utc
            self.repository.store_trade(trade)
            return trade
        favorable = bar.high - fill if trade.side == Side.LONG else fill - bar.low
        adverse = fill - bar.low if trade.side == Side.LONG else bar.high - fill
        trade.mfe_r = max(trade.mfe_r, favorable / risk_per_share)
        trade.mae_r = max(trade.mae_r, adverse / risk_per_share)
        stop_hit = bar.low <= trade.stop_current if trade.side == Side.LONG else bar.high >= trade.stop_current
        target_hit = bar.high >= trade.targets[0] if trade.side == Side.LONG else bar.low <= trade.targets[0]
        if stop_hit:  # Pessimistic resolution also covers same-bar TP/SL.
            pnl = (trade.stop_current - fill) * trade.remaining_shares * (1 if trade.side == Side.LONG else -1)
            trade.realized_r += pnl / max(trade.risk_dollars, .01)
            trade.remaining_shares = 0
            is_breakeven = abs(trade.stop_current - fill) <= self.settings.get("stops.minimum_tick_buffer", .01)
            trade.status, trade.exit_reason = "closed", "breakeven_stop" if is_breakeven else "stop_loss"
            trade.closed_at_utc = bar.bar_end_utc
        elif target_hit:
            close_shares = max(1, round(trade.shares * self.settings.get("targets.partials", [.33])[0]))
            close_shares = min(close_shares, trade.remaining_shares)
            pnl = (trade.targets[0] - fill) * close_shares * (1 if trade.side == Side.LONG else -1)
            trade.realized_r += pnl / max(trade.risk_dollars, .01)
            trade.remaining_shares -= close_shares
            trade.tp1_at_utc = trade.tp1_at_utc or bar.bar_end_utc
            trade.status = "partial" if trade.remaining_shares else "closed"
            if self.settings.get("targets.breakeven_default") == "after_TP1":
                trade.stop_current = fill
            trade.exit_reason = "tp1" if trade.status == "closed" else None
            if trade.status == "closed":
                trade.closed_at_utc = bar.bar_end_utc
        self.repository.store_trade(trade)
        return trade


class VariantRecorder:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings, self.repository = settings, repository

    def record(self, setup: SetupEvent, score_variants: dict[str, dict[str, float]]) -> int:
        count = 0
        for value in self.settings.get("stops.variants", []):
            self.repository.store_variant(setup.setup_event_id, "stop_buffer_atr", str(value), {"value": value})
            count += 1
        for value in self.settings.get("targets.breakeven_variants", []):
            self.repository.store_variant(setup.setup_event_id, "breakeven", str(value), {"value": value})
            count += 1
        for value in self.settings.get("targets.logic_variants", []):
            self.repository.store_variant(setup.setup_event_id, "tp_logic", str(value), {"value": value})
            count += 1
        for value in ("close_reclaim", "reclaim_plus_retest", "aggressive_intrabar_reclaim"):
            self.repository.store_variant(setup.setup_event_id, "entry_logic", value, {"value": value})
            count += 1
        for name, weights in score_variants.items():
            self.repository.store_variant(setup.setup_event_id, "score_weight_set", name, {"weights": weights})
            count += 1
        return count
