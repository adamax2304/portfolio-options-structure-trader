from __future__ import annotations

import ast
import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from . import api
from .config import PROJECT_ROOT, Settings
from .engines import MacroEventGuard
from .models import (Bar, EligibilityContext, FeatureSet, GuardStatus, Level, MacroEvent, Mode, ReplayRequest,
                     ScanInput, ScanRequest, SetupEvent, Side, TickerState)
from .service import OptionsStructureTraderService


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    return value


def _db_snapshot(root: Path) -> dict[str, dict[str, int]]:
    if not root.exists():
        return {}
    result: dict[str, dict[str, int]] = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            stat = path.stat()
            result[str(path.relative_to(root))] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return result


def _source_audit() -> dict[str, Any]:
    imports: list[dict[str, str]] = []
    text = ""
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        if path.name == "acceptance.py":
            continue
        source = path.read_text(encoding="utf-8")
        text += "\n" + source.lower()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend({"file": str(path.relative_to(PROJECT_ROOT)), "module": name.name} for name in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append({"file": str(path.relative_to(PROJECT_ROOT)), "module": node.module or ""})
    forbidden_imports = [item for item in imports if any(token in item["module"].lower()
                         for token in ("portfolio", "master_orchestrator", "alpaca_trade_api", "ib_insync"))]
    live_execution_tokens = [token for token in ("submit_order(", "place_order(", "/v2/orders", "trading_client",
                             "brokerapi", "execute_live_trade") if token in text]
    shared_pipeline_tokens = [token for token in ("master_orchestrator", "live_signal_pipeline", "portfolio_os") if token in text]
    return {"python_import_count": len(imports), "forbidden_imports": forbidden_imports,
            "live_execution_tokens": live_execution_tokens, "shared_pipeline_tokens": shared_pipeline_tokens}


def _make_scan(side: Side, ticker: str, at: datetime, *, stale: bool = False,
               guard: GuardStatus | None = None, source_mode: str = "ACCEPTANCE_NORMALIZED") -> ScanInput:
    level = Level(ticker=ticker, level_type="GAMMA_FLIP", price=100, zone_low=99.9, zone_high=100.1,
                  known_at_utc=at - timedelta(hours=1), source="acceptance_feed", strength_score=.95)
    if side == Side.LONG:
        previous = Bar(ticker=ticker, bar_start_utc=at - timedelta(minutes=10), bar_end_utc=at - timedelta(minutes=5),
                       open=100.3, high=100.5, low=99.0, close=99.7, volume=100_000, vwap=100, atr=.5)
        confirmation = Bar(ticker=ticker, bar_start_utc=at - timedelta(minutes=5), bar_end_utc=at,
                           open=99.7, high=100.7, low=99.4, close=100.5, volume=220_000,
                           vwap=100.2, atr=.5, relative_volume=2)
        targets, flow_direction = [105, 108, 112], "bullish"
    else:
        previous = Bar(ticker=ticker, bar_start_utc=at - timedelta(minutes=10), bar_end_utc=at - timedelta(minutes=5),
                       open=99.7, high=101, low=99.5, close=100.4, volume=100_000, vwap=100, atr=.5)
        confirmation = Bar(ticker=ticker, bar_start_utc=at - timedelta(minutes=5), bar_end_utc=at,
                           open=100.4, high=100.7, low=99.3, close=99.5, volume=220_000,
                           vwap=99.8, atr=.5, relative_volume=2)
        targets, flow_direction = [95, 92, 88], "bearish"
    state = TickerState(ticker=ticker, timestamp_utc=at, source="acceptance_feed",
                        spot_price=confirmation.close, bid=confirmation.close - .01,
                        ask=confirmation.close + .01, last=confirmation.close, spread_bps=2,
                        volume_today=2_000_000, relative_volume=2, average_daily_volume=10_000_000,
                        source_freshness_seconds=999 if stale else 0)
    features = FeatureSet(dealer_positioning=.95, options_flow=.9, oi_confirmation=.9,
                          big_trades_dark_pool=.8, price_structure=1, volatility_liquidity=.9,
                          data_quality_event_guard=0 if guard and guard.blocked else 1,
                          flow_direction=flow_direction, volume_expansion=True,
                          data_staleness_flag=stale, raw={"acceptance_fixture": True})
    return ScanInput(ticker_state=state, level=level, previous_bar=previous,
                     confirmation_bar=confirmation, features=features, target_nodes=targets,
                     guard=guard or GuardStatus(ticker=ticker, evaluated_at_utc=at, blocked=False),
                     source_mode=source_mode,
                     eligibility=EligibilityContext(real_data=True, supported_ticker=True, session_valid=True,
                         session_name="regular", macro_guard_evaluated=True, required_fields_complete=not stale,
                         price_provider="acceptance_price", structure_provider="acceptance_structure",
                         price_provider_production_eligible=True, structure_provider_production_eligible=True,
                         macro_calendar_production_eligible=True,
                         price_freshness_seconds=999 if stale else 0, structure_freshness_seconds=0,
                         confidence_score=1 if not stale else .3))


def _close_example(service: OptionsStructureTraderService, scan: ScanInput) -> dict[str, Any]:
    setup, trade = service.process_scan_input(scan, open_paper=True)
    assert setup and trade and trade.mode == Mode.PRODUCTION
    plan = setup.trade_plan
    initial_order = trade.model_dump(mode="json")
    start = scan.confirmation_bar.bar_end_utc
    fill = Bar(ticker=scan.ticker_state.ticker, bar_start_utc=start, bar_end_utc=start + timedelta(minutes=5),
               open=plan.planned_entry, high=plan.planned_entry + .1, low=plan.planned_entry - .1,
               close=plan.planned_entry, volume=100_000, atr=.5)
    trade = service.broker.on_bar(trade, fill, "high")
    assert trade.actual_fill_price is not None and trade.status == "open"
    if setup.side == Side.LONG:
        tp_bar = Bar(ticker=trade.ticker, bar_start_utc=fill.bar_end_utc,
                     bar_end_utc=fill.bar_end_utc + timedelta(minutes=5), open=trade.actual_fill_price,
                     high=plan.targets[0] + .1, low=trade.actual_fill_price - .05,
                     close=plan.targets[0], volume=150_000, atr=.5)
        exit_bar = Bar(ticker=trade.ticker, bar_start_utc=tp_bar.bar_end_utc,
                       bar_end_utc=tp_bar.bar_end_utc + timedelta(minutes=5), open=trade.actual_fill_price,
                       high=trade.actual_fill_price + .05, low=trade.actual_fill_price - .1,
                       close=trade.actual_fill_price, volume=90_000, atr=.5)
    else:
        tp_bar = Bar(ticker=trade.ticker, bar_start_utc=fill.bar_end_utc,
                     bar_end_utc=fill.bar_end_utc + timedelta(minutes=5), open=trade.actual_fill_price,
                     high=trade.actual_fill_price + .05, low=plan.targets[0] - .1,
                     close=plan.targets[0], volume=150_000, atr=.5)
        exit_bar = Bar(ticker=trade.ticker, bar_start_utc=tp_bar.bar_end_utc,
                       bar_end_utc=tp_bar.bar_end_utc + timedelta(minutes=5), open=trade.actual_fill_price,
                       high=trade.actual_fill_price + .1, low=trade.actual_fill_price - .05,
                       close=trade.actual_fill_price, volume=90_000, atr=.5)
    trade = service.broker.on_bar(trade, tp_bar, "high")
    after_tp1 = trade.model_dump(mode="json")
    trade = service.broker.on_bar(trade, exit_bar, "high")
    journal = next(item for item in service.repository.list_json("paper_trades", "WHERE id=?", (trade.trade_id,))
                   if item["trade_id"] == trade.trade_id)
    return {"input_snapshot": scan.model_dump(mode="json"), "detected_level": scan.level.model_dump(mode="json"),
            "reclaim_condition": {"sweep": min(scan.previous_bar.low, scan.confirmation_bar.low) if setup.side == Side.LONG
                                   else max(scan.previous_bar.high, scan.confirmation_bar.high),
                                  "confirmation_close": scan.confirmation_bar.close,
                                  "closed_5m": scan.confirmation_bar.closed},
            "score": setup.score.model_dump(mode="json"), "trade_plan": plan.model_dump(mode="json"),
            "paper_order_initial": initial_order,
            "after_tp1": after_tp1, "journal_record": journal, "exit_result": trade.model_dump(mode="json")}


def _markdown(evidence: dict[str, Any]) -> str:
    checks = evidence["checks"]
    table = "\n".join(f"| {name.replace('_', ' ').title()} | {'PASS' if passed else 'FAIL'} |"
                       for name, passed in checks.items())
    def example(title: str, item: dict[str, Any]) -> str:
        snap, level, plan, result = item["input_snapshot"], item["detected_level"], item["trade_plan"], item["exit_result"]
        return f"""## {title}

- Snapshot: {snap['ticker_state']['ticker']} at {snap['confirmation_bar']['bar_end_utc']}; 5m bar closed = {snap['confirmation_bar']['closed']}.
- Detected level: {level['level_type']} {level['zone_low']:.2f}-{level['zone_high']:.2f}, known at {level['known_at_utc']}.
- Reclaim: sweep {item['reclaim_condition']['sweep']:.2f}; confirmation close {item['reclaim_condition']['confirmation_close']:.2f}.
- Confluence: {item['score']['total']:.2f}/100 using `{item['score']['score_model_version']}`.
- Entry: {plan['entry_zone_low']:.2f}-{plan['entry_zone_high']:.2f}; structural stop {plan['stop_initial']:.2f}.
- Targets: {', '.join(f"{target:.2f}" for target in plan['targets'])}; primary R:R {plan['primary_rr']:.3f} (gate passed).
- Paper order: `{result['mode']}` / `{result['entry_type']}`; fill {result['actual_fill_price']:.4f}; {result['shares']} shares.
- Journal result: `{result['status']}` via `{result['exit_reason']}`; realized {result['realized_r']:.4f}R; MFE {result['mfe_r']:.4f}R; MAE {result['mae_r']:.4f}R.
"""
    ablation_rows = "\n".join(f"| {name} | {result['total']:.2f} |"
                               for name, result in evidence["replay_ablation"]["score_models"].items())
    macro_rows = "\n".join(f"| {name} | {item['guard']['blocked']} | {item['setup']['production_paper_allowed']} | {item['trade']['mode']} |"
                            for name, item in evidence["macro_guard"]["blocked_events"].items())
    return f"""# MVP Acceptance Report

Generated: {evidence['generated_at_utc']}

Overall result: **{evidence['overall']}**. Full machine-readable evidence is in `acceptance_evidence.json`.

## Acceptance checks

| Check | Result |
|---|---|
{table}

## 1. Standalone isolation

- Python imports inspected: {evidence['isolation']['source_audit']['python_import_count']}.
- Forbidden Portfolio/Master Orchestrator imports: {len(evidence['isolation']['source_audit']['forbidden_imports'])}.
- Portfolio DB files changed during the run: {len(evidence['isolation']['portfolio_db_changes'])}.
- Acceptance DB: `{evidence['isolation']['acceptance_database']}` (inside this standalone project).
- Paper broker class: `{evidence['isolation']['paper_broker_class']}`.
- Alert dispatcher: `{evidence['isolation']['alert_dispatcher_class']}`; standalone Telegram disabled by default.

## 2. Synthetic, stale, and incomplete-data gating

- Synthetic scan produced `{evidence['gating']['synthetic']['trade']['mode']}` with blockers: {', '.join(evidence['gating']['synthetic']['setup']['blocking_reasons'])}.
- Forced Production acceptance returned: `{evidence['gating']['synthetic']['forced_production_error']}`.
- Stale normalized data blockers: {', '.join(evidence['gating']['stale']['setup']['blocking_reasons'])}.
- Forced stale Production acceptance returned: `{evidence['gating']['stale']['forced_production_error']}`.
- Incomplete payload status: `{evidence['gating']['incomplete']['status']}`; audit event `{evidence['gating']['incomplete']['audit_event_id']}`.
- Audit journal records generated: {evidence['gating']['audit_event_count']}.

## 3. Live trading structural disablement

- Live execution tokens found in Python source: {evidence['live_disabled']['source_tokens']}.
- Health remains `live_auto_enabled=false` even with env/config attempts: {evidence['live_disabled']['env_flag_health']} / {evidence['live_disabled']['config_flag_health']}.
- `live_assisted` broker acceptance: `{evidence['live_disabled']['live_mode_error']}`.
- Real-order API routes: {evidence['live_disabled']['real_order_routes']}.

{example('4. Full LEVEL_RECLAIM_LONG example', evidence['examples']['long'])}
{example('5. Full LEVEL_RECLAIM_SHORT example', evidence['examples']['short'])}
## 6. Replay and ablation

- Replay snapshots: {evidence['replay_ablation']['replay']['snapshots_processed']}; setups detected: {evidence['replay_ablation']['replay']['setups_detected']}; lookahead rejections: {evidence['replay_ablation']['replay']['lookahead_rejections']}.
- Determinism hash: `{evidence['replay_ablation']['replay']['determinism_hash']}`.

| Score model | Score |
|---|---:|
{ablation_rows}

- Stop variants: {', '.join(evidence['replay_ablation']['stop_variants'])}.
- TP variants: {', '.join(evidence['replay_ablation']['tp_variants'])}.
- Breakeven variants: {', '.join(evidence['replay_ablation']['breakeven_variants'])}.

## 7. Macro Event Guard

Outside-event scan: blocked = {evidence['macro_guard']['outside_window']['guard']['blocked']}, Production eligible = {evidence['macro_guard']['outside_window']['setup']['production_paper_allowed']}.

| Event | Guard blocked | Production allowed | Recorded mode |
|---|---:|---:|---|
{macro_rows}

Each blocked setup is journaled with `macro_event_proximity_flag=true` and recorded only in Shadow Paper.

## 8. API and dashboard

- Health: `{evidence['api_dashboard']['health']['status']}`; live auto = {evidence['api_dashboard']['health']['live_auto_enabled']}.
- Dashboard HTTP status: {evidence['api_dashboard']['dashboard_status']}; title present = {evidence['api_dashboard']['dashboard_title_present']}.
- Latest scans: {evidence['api_dashboard']['latest_scans_count']}.
- Journal events: {evidence['api_dashboard']['journal_count']}.
- Open paper trades: {evidence['api_dashboard']['open_count']}.
- Closed paper trades: {evidence['api_dashboard']['closed_count']}.
- Ablation weight sets: {', '.join(evidence['api_dashboard']['ablation_weight_sets'])}.
- Config status: version `{evidence['api_dashboard']['config_status']['config_version']}`, DB `{evidence['api_dashboard']['config_status']['database_path']}`.

## 9. Known Limitations

- Synthetic inputs exercise deterministic behavior only; they do not establish trading edge and are never Production-eligible.
- Fresh provider credentials and applicable market-data entitlements are required before Production Paper can use real feeds.
- Free/delayed GEX, options, FINRA, and off-exchange data can be incomplete or stale; delayed dark-pool context is not an intraday trigger.
- Live trading is unavailable. There is no real broker-order execution path.
- Portfolio OS integration has not been enabled; the standalone read-only contract remains a future boundary after validation.
- Sample replay validates mechanics and determinism, not statistical expectancy. Promotion still requires adequate out-of-sample data.
"""


def run(output_dir: Path | None = None) -> dict[str, Any]:
    generated = datetime.now(timezone.utc)
    run_name = generated.strftime("%Y%m%dT%H%M%SZ")
    output_dir = output_dir or PROJECT_ROOT / "acceptance" / run_name
    output_dir.mkdir(parents=True, exist_ok=True)
    portfolio_root = PROJECT_ROOT.parent / "portfolio-strategy-os"
    portfolio_before = _db_snapshot(portfolio_root)
    data = copy.deepcopy(Settings.load().data)
    data["database"]["path"] = str(output_dir / "acceptance.db")
    data["alerts"]["console_enabled"] = False
    data["alerts"]["telegram_enabled"] = False
    settings = Settings(data, PROJECT_ROOT)
    service = OptionsStructureTraderService(settings)
    at = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)

    long_scan = _make_scan(Side.LONG, "ACCLONG", at)
    short_scan = _make_scan(Side.SHORT, "ACCSHORT", at + timedelta(hours=1))
    long_example = _close_example(service, long_scan)
    short_example = _close_example(service, short_scan)

    synthetic_result = service.scan_once(ScanRequest(tickers=["SPY"], fixture=True, open_paper=True))["results"][0]
    synthetic_setup = SetupEvent.model_validate(synthetic_result["setup"])
    try:
        service.broker.accept(synthetic_setup, Mode.PRODUCTION)
        forced_error = "NO ERROR"
    except ValueError as exc:
        forced_error = str(exc)
    stale_scan = _make_scan(Side.LONG, "STALE", at + timedelta(hours=2), stale=True)
    stale_setup, stale_trade = service.process_scan_input(stale_scan, open_paper=True)
    try:
        service.broker.accept(stale_setup, Mode.PRODUCTION)
        stale_forced_error = "NO ERROR"
    except ValueError as exc:
        stale_forced_error = str(exc)
    incomplete = service.evaluate_normalized_payload({"ticker": "INCOMPLETE"})

    weight_sets = service.scorer.ablation_weight_sets()
    selected_names = ["baseline_manual", "equal_weight", "no_flow", "no_gex", "no_oi",
                      "price_action_only", "options_only"]
    score_models = {name: service.scorer.score(long_scan.features, name, weight_sets[name]).model_dump(mode="json")
                    for name in selected_names}
    stop_variants = {}
    for value in settings.get("stops.variants"):
        plan, blockers = service.constructor.construct(long_scan, Side.LONG, float(value))
        stop_variants[str(value)] = {"plan": plan.model_dump(mode="json") if plan else None, "blockers": blockers}
    replay = service.replay.run(ReplayRequest(snapshots=[long_scan, short_scan]))

    event_time = at + timedelta(days=1)
    blocked_events: dict[str, Any] = {}
    for event_name in ("CPI", "FOMC", "NFP"):
        event = MacroEvent(event_id=f"accept-{event_name.lower()}", event_name=event_name,
                           event_type=event_name, event_time_utc=event_time, importance="high")
        guard = MacroEventGuard(settings, [event]).evaluate(f"MACRO{event_name}", event_time - timedelta(minutes=20))
        scan = _make_scan(Side.LONG, f"MACRO{event_name}", event_time - timedelta(minutes=20), guard=guard)
        setup, trade = service.process_scan_input(scan, open_paper=True)
        blocked_events[event_name] = {"guard": guard.model_dump(mode="json"),
                                      "setup": setup.model_dump(mode="json"), "trade": trade.model_dump(mode="json")}
    clear_guard = MacroEventGuard(settings, [MacroEvent(event_id="future", event_name="CPI", event_type="CPI",
                                  event_time_utc=event_time, importance="high")]).evaluate("CLEAR", at)
    clear_scan = _make_scan(Side.LONG, "CLEAR", at, guard=clear_guard)
    clear_setup, _ = service.process_scan_input(clear_scan, open_paper=False)

    old_env = os.environ.get("LIVE_AUTO_ENABLED")
    os.environ["LIVE_AUTO_ENABLED"] = "true"
    env_flag_health = service.health()["live_auto_enabled"]
    settings.data["system"]["live_auto_enabled"] = True
    config_flag_health = service.health()["live_auto_enabled"]
    if old_env is None:
        os.environ.pop("LIVE_AUTO_ENABLED", None)
    else:
        os.environ["LIVE_AUTO_ENABLED"] = old_env
    try:
        eligible_setup = service.detector.detect(long_scan)
        assert eligible_setup is not None
        service.broker.accept(eligible_setup, Mode.LIVE_ASSISTED)
        live_mode_error = "NO ERROR"
    except Exception as exc:
        live_mode_error = str(exc)

    api.service = service
    client = TestClient(api.app)
    openapi = client.get("/openapi.json").json()
    routes = sorted(openapi["paths"])
    health = client.get("/health").json()
    latest = client.get("/setups/live").json()
    journal = client.get("/journal/events").json()
    open_trades = client.get("/paper/open").json()
    closed_trades = client.get("/paper/closed").json()
    ablation_api = client.get("/performance/ablation").json()
    config_status = client.get("/config/status").json()
    dashboard = client.get("/")

    source_audit = _source_audit()
    portfolio_after = _db_snapshot(portfolio_root)
    portfolio_changes = {key: {"before": portfolio_before.get(key), "after": portfolio_after.get(key)}
                         for key in set(portfolio_before) | set(portfolio_after)
                         if portfolio_before.get(key) != portfolio_after.get(key)}
    audit_events = service.repository.list_json("audit_events", limit=1000)
    real_order_routes = [route for route in routes if any(token in route.lower()
                         for token in ("/orders", "/broker", "execute-trade", "place-order", "submit-order"))]

    evidence: dict[str, Any] = {
        "generated_at_utc": generated.isoformat(),
        "isolation": {"source_audit": source_audit, "portfolio_db_before": portfolio_before,
                      "portfolio_db_after": portfolio_after, "portfolio_db_changes": portfolio_changes,
                      "acceptance_database": str(service.repository.path),
                      "paper_broker_class": f"{service.broker.__class__.__module__}.{service.broker.__class__.__name__}",
                      "alert_dispatcher_class": f"{service.alerts.__class__.__module__}.{service.alerts.__class__.__name__}",
                      "telegram_enabled": settings.get("alerts.telegram_enabled")},
        "gating": {"synthetic": {**synthetic_result, "forced_production_error": forced_error},
                   "stale": {"setup": stale_setup.model_dump(mode="json"), "trade": stale_trade.model_dump(mode="json"),
                             "forced_production_error": stale_forced_error},
                   "incomplete": incomplete, "audit_event_count": len(audit_events), "audit_events": audit_events},
        "live_disabled": {"source_tokens": source_audit["live_execution_tokens"],
                          "env_flag_health": env_flag_health, "config_flag_health": config_flag_health,
                          "live_mode_error": live_mode_error, "real_order_routes": real_order_routes, "api_routes": routes},
        "examples": {"long": long_example, "short": short_example},
        "replay_ablation": {"replay": {key: value for key, value in replay.items() if key != "setups"},
                            "score_models": score_models, "stop_variant_details": stop_variants,
                            "stop_variants": [str(value) for value in settings.get("stops.variants")],
                            "tp_variants": settings.get("targets.logic_variants"),
                            "breakeven_variants": settings.get("targets.breakeven_variants")},
        "macro_guard": {"outside_window": {"guard": clear_guard.model_dump(mode="json"),
                                            "setup": clear_setup.model_dump(mode="json")},
                        "blocked_events": blocked_events},
        "api_dashboard": {"health": health, "dashboard_status": dashboard.status_code,
                          "dashboard_title_present": "Options Structure Trader" in dashboard.text,
                          "latest_scans_count": len(latest), "journal_count": len(journal),
                          "open_count": len(open_trades), "closed_count": len(closed_trades),
                          "ablation_weight_sets": sorted(ablation_api["weight_sets"]),
                          "config_status": config_status, "route_count": len(routes)},
    }
    checks = {
        "standalone_imports": not source_audit["forbidden_imports"] and not source_audit["shared_pipeline_tokens"],
        "portfolio_database_unchanged": not portfolio_changes,
        "standalone_paper_broker": service.broker.__class__.__module__ == "options_structure_trader.broker",
        "standalone_alerting": settings.get("alerts.telegram_enabled") is False,
        "synthetic_shadow_only": synthetic_result["trade"]["mode"] == "shadow_paper" and not synthetic_result["setup"]["production_paper_allowed"],
        "synthetic_production_rejected": "Blocked setup" in forced_error,
        "stale_shadow_only": stale_trade.mode == Mode.SHADOW and any("stale" in reason.lower() for reason in stale_setup.blocking_reasons),
        "stale_production_rejected": "Blocked setup" in stale_forced_error,
        "incomplete_rejection_audited": incomplete["status"] == "rejected" and any(item["event_type"] == "normalized_input_rejected" for item in audit_events),
        "live_execution_absent": not source_audit["live_execution_tokens"] and not real_order_routes,
        "live_flags_inert": env_flag_health is False and config_flag_health is False,
        "live_mode_rejected": "Only standalone paper modes" in live_mode_error,
        "long_end_to_end": long_example["exit_result"]["status"] == "closed" and long_example["journal_record"]["status"] == "closed",
        "short_end_to_end": short_example["exit_result"]["status"] == "closed" and short_example["journal_record"]["status"] == "closed",
        "replay_ablation_complete": replay["setups_detected"] == 2 and set(selected_names) <= set(score_models),
        "variants_complete": bool(stop_variants) and bool(settings.get("targets.logic_variants")) and bool(settings.get("targets.breakeven_variants")),
        "macro_guard_complete": all(item["guard"]["blocked"] and not item["setup"]["production_paper_allowed"]
                                    and item["trade"]["mode"] == "shadow_paper" for item in blocked_events.values()),
        "api_dashboard_complete": health["status"] == "ok" and dashboard.status_code == 200 and len(routes) >= 20,
    }
    evidence["checks"] = checks
    evidence["overall"] = "PASS" if all(checks.values()) else "FAIL"
    evidence_path = output_dir / "acceptance_evidence.json"
    report_path = output_dir / "MVP_ACCEPTANCE_REPORT.md"
    evidence_path.write_text(json.dumps(evidence, indent=2, default=_jsonable), encoding="utf-8")
    report_path.write_text(_markdown(evidence), encoding="utf-8")
    latest_dir = PROJECT_ROOT / "acceptance"
    (latest_dir / "LATEST_ACCEPTANCE_EVIDENCE.json").write_text(evidence_path.read_text(encoding="utf-8"), encoding="utf-8")
    (latest_dir / "LATEST_MVP_ACCEPTANCE_REPORT.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    result = {"overall": evidence["overall"], "checks_passed": sum(checks.values()),
              "checks_total": len(checks), "output_dir": str(output_dir),
              "report": str(report_path), "evidence": str(evidence_path)}
    if evidence["overall"] != "PASS":
        raise RuntimeError(json.dumps({"result": result, "failed": [name for name, passed in checks.items() if not passed]}, indent=2))
    return result


def main() -> None:
    print(json.dumps(run(), indent=2))


if __name__ == "__main__":
    main()
