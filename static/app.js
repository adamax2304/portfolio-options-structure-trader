const $ = id => document.getElementById(id);
const money = value => Number(value).toFixed(2);
const maybeMoney = value => value === null || value === undefined ? '—' : money(value);
const maybeR = value => value === null || value === undefined ? '—' : Number(value).toFixed(2);
const maybePct = value => value === null || value === undefined ? '—' : `${Math.round(Number(value) * 100)}%`;
const when = value => value ? new Date(value).toLocaleString() : '—';

async function json(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function loadTicker(result) {
  const setup = result.setup;
  if (!setup) return;
  $('signalEmpty').classList.add('hidden');
  $('signal').classList.remove('hidden');
  $('score').textContent = Math.round(setup.score.total);
  $('setupType').textContent = setup.setup_type;
  $('reasons').textContent = setup.reason.join(' · ');
  if (setup.trade_plan) {
    $('entry').textContent = `${money(setup.trade_plan.entry_zone_low)}–${money(setup.trade_plan.entry_zone_high)}`;
    $('stop').textContent = money(setup.trade_plan.stop_initial);
    $('targets').textContent = setup.trade_plan.targets.map(money).join(' / ');
    $('rr').textContent = `${setup.trade_plan.primary_rr.toFixed(2)}R`;
  }
  const lane = setup.recommended_mode;
  $('blockers').textContent = setup.blocking_reasons.length ? setup.blocking_reasons.join(' · ') : 'All lane requirements passed';
  $('signalBadge').textContent = lane.replaceAll('_', ' ').toUpperCase();
  $('signalBadge').className = `badge ${lane === 'production_paper' ? 'good' : lane === 'free_validation_paper' ? 'warn' : ''}`;
  $('selectedTicker').textContent = setup.ticker;
  $('spot').textContent = `Closed-candle snapshot · ${when(setup.created_at_utc)}`;
  const level = setup.signal_snapshot.level;
  $('gammaFlip').textContent = money(level.price);
  $('guard').textContent = setup.signal_snapshot.guard?.blocked ? 'BLOCKED' : setup.signal_snapshot.guard?.macro_unknown ? 'UNKNOWN' : 'CLEAR';
}

async function refreshObservation() {
  const status = await json('/observation/status');
  const target = status.targets.free_validation_valid_scans;
  $('freeScans').textContent = `${status.free_validation_valid_scans} / ${target}`;
  $('freeTrades').textContent = status.free_validation_paper_trades;
  $('validScans').textContent = status.valid_production_data_scans;
  $('shadowObservations').textContent = status.shadow_only_observations;
  $('macroApproval').textContent = status.macro_calendar_approved ? 'APPROVED' : 'UNAPPROVED';
  $('missingOptions').textContent = status.missing_oi_greeks_count;
  $('staleCandles').textContent = status.stale_candle_count;
  $('unofficialWarning').textContent = status.unofficial_source_warning ? 'LIMITED' : 'CLEAR';
  $('liveDisabled').textContent = status.live_trading_disabled ? 'DISABLED' : 'ERROR';
  const done = status.progress.free_validation_scans_remaining === 0;
  $('observationBadge').textContent = done ? 'SCAN TARGET MET' : 'COLLECTING';
  $('observationBadge').className = `badge ${done ? 'good' : 'warn'}`;
  $('observationStatus').textContent = `${status.progress.free_validation_scans_remaining} unique Phase 2C scans remain. Optimization ${status.optimization_locked ? 'locked' : 'sample threshold reached'}.`;
}

async function refreshDaemon() {
  const status = await json('/scheduler/status');
  $('daemonStatus').textContent = status.daemon_status;
  $('sessionState').textContent = status.current_session_state;
  $('nextOpen').textContent = when(status.next_rth_open);
  $('nextClose').textContent = when(status.next_rth_close);
  $('lastScan').textContent = when(status.last_scan_time);
  $('nextScan').textContent = when(status.next_scan_time);
  $('scansToday').textContent = status.scans_today || 0;
  $('daemonFreeToday').textContent = status.free_validation_scans_today || 0;
  $('daemonShadowToday').textContent = status.shadow_scans_today || 0;
  $('daemonProductionToday').textContent = status.production_scans_today || 0;
  $('dailyReportStatus').textContent = (status.daily_report_status || 'pending').toUpperCase();
  const providerTimes = (status.provider_status || []).map(item => item.last_success_utc).filter(Boolean).sort();
  $('providerFreshness').textContent = providerTimes.length ? when(providerTimes.at(-1)) : 'NO LIVE FETCH YET';
  $('daemonError').textContent = status.last_error || 'None';
  $('daemonLiveDisabled').textContent = status.live_trading_disabled ? 'DISABLED' : 'ERROR';
  const healthy = ['RUNNING', 'WAITING_FOR_NEXT_CYCLE', 'SLEEPING'].includes(status.daemon_status);
  $('daemonBadge').textContent = status.daemon_status;
  $('daemonBadge').className = `badge ${healthy ? 'good' : 'warn'}`;
  $('providerFailuresToday').textContent = status.provider_failures_today || 0;
  $('symbolsValidToday').textContent = status.symbols_valid_today || 0;
  $('symbolsBlockedToday').textContent = status.symbols_blocked_today || 0;
}

async function refreshWatchlist() {
  const status = await json('/watchlist/status');
  $('watchlistCount').textContent = `${status.configured_symbols} SYMBOLS`;
  $('watchlistRows').innerHTML = status.symbols.map(row => `<tr>
    <td>${row.symbol}</td><td>${row.tier.replaceAll('_', ' ')}</td>
    <td class="${row.status === 'ACTIVE' ? 'status-active' : 'status-blocked'}">${row.status}</td>
    <td>${row.last_outcome || '—'}</td><td>${row.failures_today || 0}</td></tr>`).join('');
  const picker = $('ticker');
  if (!picker.options.length) status.symbols.filter(row => row.enabled).forEach(row => picker.add(new Option(row.symbol, row.symbol)));
}

async function refreshPhase2d() {
  const payload = await json('/reports/phase-2d');
  const report = payload.report;
  $('phase2dScans').textContent = `${report.free_validation_scans} / ${report.target_free_validation_scans}`;
  $('tier1Scans').textContent = `${report.tier1_scans} / ${report.target_tier1_scans}`;
  $('validSymbols').textContent = `${report.valid_symbols} / ${report.target_valid_symbols}`;
  $('phase2dBadge').textContent = report.status.replaceAll('_', ' ');
  $('phase2dBadge').className = `badge ${report.status === 'PASSED' ? 'good' : 'warn'}`;
}

async function refreshFreshness() {
  const payload = await json('/market-data/freshness');
  const metrics = payload.metrics || {};
  $('yfFreshness').textContent = `${metrics.yfinance_fresh || 0} / ${metrics.yfinance_stale || 0}`;
  $('fhFreshness').textContent = metrics.finnhub_fresh_quotes || 0;
  $('avFallback').textContent = `${metrics.fallback_successes || 0} / ${metrics.fallback_attempts || 0}`;
  $('crossConflicts').textContent = metrics.cross_provider_conflicts || 0;
  const healthy = (metrics.cross_provider_conflicts || 0) === 0;
  $('freshnessBadge').textContent = healthy ? 'TRACKING' : 'CHECK';
  $('freshnessBadge').className = `badge ${healthy ? 'good' : 'warn'}`;
  $('freshnessRows').innerHTML = (payload.symbols || []).slice(0, 80).map(row => `<tr>
    <td>${row.symbol}</td>
    <td>${(row.tier || 'unknown').replaceAll('_', ' ')}</td>
    <td>${row.selected_candle_provider || 'None'}</td>
    <td>${when(row.latest_completed_candle)}</td>
    <td>${when(row.expected_completed_candle)}</td>
    <td>${row.candle_lag_seconds ?? '—'}</td>
    <td>${row.finnhub_quote_age_seconds ?? '—'}</td>
    <td>${row.fallback_used ? 'YES' : 'NO'}</td>
    <td>${(row.provider_attempts || []).join(' → ') || '—'}</td>
    <td class="${row.status === 'VALID' ? 'status-active' : 'status-blocked'}">${row.status}</td>
  </tr>`).join('');
}

async function refreshPaperStatus() {
  const payload = await json('/paper/status');
  const summary = payload.summary || {};
  $('paperValidScans').textContent = summary.total_valid_rth_scans || 0;
  $('paperNaturalSetups').textContent = summary.natural_reclaim_setups_detected || 0;
  $('paperUniqueEvents').textContent = summary.unique_reclaim_events || 0;
  $('paperFreeValidationTrades').textContent = summary.free_validation_trades || 0;
  $('paperEntriesOpened').textContent = summary.paper_entries_opened || 0;
  $('paperEntriesClosed').textContent = summary.paper_entries_closed || 0;
  $('paperWlb').textContent = `${summary.winners || 0} / ${summary.losers || 0} / ${summary.breakevens || 0}`;
  $('paperAvgR').textContent = maybeR(summary.average_realized_r);
  $('paperAvgWinnerR').textContent = maybeR(summary.average_winner_r);
  $('paperAvgLoserR').textContent = maybeR(summary.average_loser_r);
  $('paperExpectancyR').textContent = maybeR(summary.expectancy_r);
  $('paperProfitFactor').textContent = summary.profit_factor ?? '—';
  $('paperOpenRiskR').textContent = maybeR(summary.open_portfolio_risk_r);
  $('paperShadowReasons').textContent = (summary.shadow_downgrade_reasons || [])
    .slice(0, 2).map(item => `${item[0]} (${item[1]})`).join(' · ') || '—';
  $('paperAvgMfe').textContent = maybeR(summary.average_mfe);
  $('paperAvgMae').textContent = maybeR(summary.average_mae);
  $('paperStatusBadge').textContent = (payload.open_paper_trades || []).length ? 'OPEN' : 'NO OPEN';
  $('paperStatusBadge').className = `badge ${(payload.open_paper_trades || []).length ? 'warn' : 'good'}`;
  $('paperSyntheticNote').textContent = `${payload.synthetic_test_records_excluded?.paper_trades || 0} synthetic/test paper records excluded from live paper statistics.`;
  $('paperOpenRows').innerHTML = (payload.open_paper_trades || []).map(row => `<tr>
    <td>${row.symbol}<br><small>${row.setup_family}</small></td>
    <td>${row.lane}</td><td>${row.direction}</td><td>${maybeMoney(row.entry)}</td>
    <td>${maybeMoney(row.current_price)}</td><td>${maybeMoney(row.stop)}</td>
    <td>${[row.tp1, row.tp2, row.tp3].map(maybeMoney).join(' / ')}</td>
    <td>${maybeR(row.current_r)}</td><td>${maybeR(row.mfe)} / ${maybeR(row.mae)}</td><td>${row.current_status}</td>
  </tr>`).join('') || '<tr><td colspan="10">No open natural paper trades.</td></tr>';
  $('paperClosedRows').innerHTML = (payload.closed_paper_trades || []).map(row => `<tr>
    <td>${row.symbol}<br><small>${row.setup_family}</small></td><td>${row.lane}</td><td>${row.direction}</td>
    <td>${maybeMoney(row.entry)}</td><td>${maybeMoney(row.exit)}</td><td>${maybeR(row.realized_r)}</td>
    <td>${row.exit_reason || '—'}</td><td>${row.duration_minutes ?? '—'}m</td><td>${row.data_quality_tier || '—'}</td>
  </tr>`).join('') || '<tr><td colspan="9">No closed natural paper trades.</td></tr>';
  $('paperPendingRows').innerHTML = (payload.pending_setups || []).map(row => `<tr>
    <td>${row.symbol}</td><td>${row.direction}</td>
    <td>${row.detected_options_level?.type || '—'} ${maybeMoney(row.detected_options_level?.price)}</td>
    <td>${maybeR(row.confluence_score)}</td><td>${maybeR(row.confidence)}</td>
    <td>${[...(row.missing_confirmation || []), ...(row.reason_no_paper_order || [])].slice(0, 4).join(' · ') || '—'}</td>
  </tr>`).join('') || '<tr><td colspan="6">No detected setup is waiting without a paper record.</td></tr>';
  $('paperScanRows').innerHTML = (payload.recent_valid_scans || []).map(row => `<tr>
    <td>${row.symbol}</td><td>${when(row.timestamp)}</td>
    <td>${row.gex?.detected_level?.type || '—'} ${maybeMoney(row.gex?.detected_level?.price)}</td>
    <td>${maybeR(row.price_relative_to_level)}</td><td>${row.reclaim_state}</td>
    <td>${maybeR(row.score)}</td><td>${row.result}</td>
  </tr>`).join('');
}

async function refreshTradeManagementResearch() {
  const payload = await json('/trade-management/research/status');
  const summary = payload.summary || {};
  $('tmCanonicalExpectancy').textContent = maybeR(summary.canonical_expectancy);
  $('tmBestExpectancy').textContent = `${summary.best_variant || '—'} ${maybeR(summary.best_variant_expectancy)}`;
  $('tmBaselinePf').textContent = summary.baseline_profit_factor ?? '—';
  $('tmBestPf').textContent = summary.best_variant_profit_factor ?? '—';
  $('tmAvgWinnerBaseline').textContent = maybeR(summary.average_winner_baseline);
  $('tmAvgWinnerBest').textContent = maybeR(summary.average_winner_best_variant);
  $('tmReach05').textContent = maybePct(summary['pct_reaching_0.5R']);
  $('tmReach1').textContent = maybePct(summary['pct_reaching_1.0R']);
  $('tmReach15').textContent = maybePct(summary['pct_reaching_1.5R']);
  $('tmReach2').textContent = maybePct(summary['pct_reaching_2.0R']);
  $('tmBeFreq').textContent = maybePct(summary.be_exit_frequency);
  $('tmTp1Freq').textContent = maybePct(summary.tp1_only_frequency);
  $('tmTp2Freq').textContent = maybePct(summary.tp2_reach_frequency);
  $('tmTp3Freq').textContent = maybePct(summary.tp3_reach_frequency);
  $('tmBadge').textContent = 'COUNTERFACTUAL';
  $('tmBadge').className = 'badge warn';
}

async function refreshManagementAB() {
  const payload = await json('/management/ab/status');
  const branchA = (payload.branches || []).find(row => row.branch === 'A') || {};
  const branchB = (payload.branches || []).find(row => row.branch === 'B') || {};
  $('abPaired').textContent = `${payload.paired_completed_or_censored || 0} / ${payload.acceptance_target || 100}`;
  $('abNA').textContent = branchA.n || 0;
  $('abNB').textContent = branchB.n || 0;
  $('abExpectancy').textContent = `${maybeR(branchA.expectancy)} / ${maybeR(branchB.expectancy)}`;
  $('abMedian').textContent = `${maybeR(branchA.median_r)} / ${maybeR(branchB.median_r)}`;
  $('abPf').textContent = `${branchA.profit_factor ?? '—'} / ${branchB.profit_factor ?? '—'}`;
  $('abWinRate').textContent = `${maybePct(branchA.win_rate)} / ${maybePct(branchB.win_rate)}`;
  $('abAvgWinner').textContent = `${maybeR(branchA.average_winner)} / ${maybeR(branchB.average_winner)}`;
  $('abAvgLoser').textContent = `${maybeR(branchA.average_loser)} / ${maybeR(branchB.average_loser)}`;
  $('abDrawdown').textContent = `${maybeR(branchA.max_drawdown)} / ${maybeR(branchB.max_drawdown)}`;
  $('abTp1').textContent = `${maybePct(branchA.tp1_frequency)} / ${maybePct(branchB.tp1_frequency)}`;
  $('abRunner').textContent = `${maybeR(branchA.runner_contribution)} / ${maybeR(branchB.runner_contribution)}`;
  $('abBe').textContent = `${maybePct(branchA.be_frequency)} / ${maybePct(branchB.be_frequency)}`;
  $('abBadge').textContent = payload.decision_rule?.eligible_to_consider_promotion ? 'READY TO REVIEW' : 'COLLECTING';
  $('abBadge').className = `badge ${payload.decision_rule?.eligible_to_consider_promotion ? 'good' : 'warn'}`;
}

async function refreshEdgeDiscovery() {
  const payload = await json('/reports/phase-2d5-edge-discovery');
  const summary = payload.report || {};
  const dashboard = summary.dashboard || {};
  $('edgeExpectancy').textContent = maybeR(dashboard.overall_expectancy);
  $('edgePf').textContent = dashboard.overall_profit_factor ?? '—';
  $('edgeBestSubgroup').textContent = dashboard.best_preliminary_subgroup || '—';
  $('edgeWorstSubgroup').textContent = dashboard.worst_subgroup || '—';
  $('edgeLong').textContent = maybeR(dashboard.long_expectancy);
  $('edgeShort').textContent = maybeR(dashboard.short_expectancy);
  $('edgeIndex').textContent = maybeR(dashboard.index_etf_expectancy);
  $('edgeSingle').textContent = maybeR(dashboard.single_stock_expectancy);
  $('edgeBestLevel').textContent = dashboard.best_level_type || '—';
  $('edgeWorstLevel').textContent = dashboard.worst_level_type || '—';
  $('edgeBestTime').textContent = dashboard.best_time_window || '—';
  $('edgeWorstTime').textContent = dashboard.worst_time_window || '—';
  $('edgeBestScore').textContent = dashboard.best_score_bucket || '—';
  $('edgeWorstScore').textContent = dashboard.worst_score_bucket || '—';
  const counts = dashboard.candidate_counts || {};
  $('edgeCandidateCounts').textContent = Object.entries(counts).map(([key, value]) => `${key}: ${value}`).join(' · ') || '0';
  $('edgeBadge').textContent = `${summary.resolved_rows || 0} RESOLVED`;
  $('edgeBadge').className = 'badge warn';
}

async function refreshForwardEdgeValidation() {
  const payload = await json('/reports/phase-2d6-forward-edge-validation');
  const summary = payload.report || {};
  const dashboard = summary.dashboard || {};
  $('forwardEdgeLong').textContent = maybeR(dashboard.long_forward_expectancy);
  $('forwardEdgeShort').textContent = maybeR(dashboard.short_forward_expectancy);
  $('forwardEdgeWindowLong').textContent = maybeR(dashboard.long_1130_1300_expectancy);
  $('forwardEdgeLongGex').textContent = maybeR(dashboard.long_gex_node_expectancy);
  $('forwardEdgeLongGamma').textContent = maybeR(dashboard.long_gamma_flip_expectancy);
  $('forwardEdgeBest').textContent = dashboard.best_forward_cohort || '—';
  $('forwardEdgeN').textContent = dashboard.cohort_sample_size || 0;
  $('forwardEdgeRobustness').textContent = dashboard.cohort_robustness_status || '—';
  $('forwardEdgeBadge').textContent = dashboard.cohort_promotion_status || 'COLLECTING';
  $('forwardEdgeBadge').className = `badge ${dashboard.cohort_promotion_status === 'FORWARD_SUPPORTED' ? 'good' : 'warn'}`;
}

async function refreshPhase4aResearch() {
  const payload = await json('/research/multitimeframe-edge/status');
  const dashboard = payload.dashboard || {};
  const controls = dashboard.options_vs_controls || {};
  $('phase4aA').textContent = maybeR(dashboard.variant_A_expectancy);
  $('phase4aB').textContent = maybeR(dashboard.variant_B_expectancy);
  $('phase4aC').textContent = maybeR(dashboard.variant_C_expectancy);
  $('phase4aD').textContent = maybeR(dashboard.variant_D_expectancy);
  $('phase4a5m').textContent = `${maybeR(dashboard.five_min_confirmation?.expectancy)} (${dashboard.five_min_confirmation?.N || 0})`;
  $('phase4a15m').textContent = `${maybeR(dashboard.fifteen_min_confirmation?.expectancy)} (${dashboard.fifteen_min_confirmation?.N || 0})`;
  $('phase4aPersistent').textContent = `${maybeR(dashboard.persistent_levels?.expectancy)} (${dashboard.persistent_levels?.N || 0})`;
  $('phase4aRaw').textContent = `${maybeR(dashboard.raw_levels?.expectancy)} (${dashboard.raw_levels?.N || 0})`;
  $('phase4aLongShort').textContent = `${maybeR(dashboard.long?.expectancy)} / ${maybeR(dashboard.short?.expectancy)}`;
  $('phase4aReclaimReject').textContent = `${maybeR(dashboard.reclaim?.expectancy)} / ${maybeR(dashboard.rejection?.expectancy)}`;
  $('phase4aControls').textContent = `${maybeR(controls.options?.expectancy)} / ${maybeR(controls.matched_controls?.expectancy)}`;
  $('phase4aBest').textContent = dashboard.best_research_variant || '—';
  $('phase4aDays').textContent = dashboard.unique_trading_days || 0;
  $('phase4aSample').textContent = dashboard.sample_status || 'INSUFFICIENT_SAMPLE';
  $('phase4aBadge').textContent = dashboard.sample_status || 'COLLECTING';
  $('phase4aBadge').className = `badge ${dashboard.sample_status === 'STATISTICALLY_USEFUL' ? 'good' : 'warn'}`;
}

async function refreshPhase4b1EdgeDecomposition() {
  const dashboard = await json('/research/edge-decomposition/status');
  $('phase4b1RawEdge').textContent = maybeR(dashboard.raw_directional_edge);
  $('phase4b1Canonical').textContent = maybeR(dashboard.canonical_expectancy);
  $('phase4b1Loss05').textContent = maybePct(dashboard.loser_reached_0_5R_rate);
  $('phase4b1Loss07').textContent = maybePct(dashboard.loser_reached_0_7R_rate);
  $('phase4b1Loss1').textContent = maybePct(dashboard.loser_reached_1R_rate);
  $('phase4b1WinnerMae').textContent = maybeR(dashboard.median_winner_MAE);
  $('phase4b1MedianMfe').textContent = maybeR(dashboard.median_MFE);
  $('phase4b1TimeMfe').textContent = dashboard.median_time_to_MFE === null || dashboard.median_time_to_MFE === undefined ? '—' : `${Number(dashboard.median_time_to_MFE).toFixed(0)}m`;
  $('phase4b1StopTight').textContent = maybePct(dashboard.stop_too_tight_rate);
  $('phase4b1StopRecovery').textContent = maybePct(dashboard.stop_then_recovery_rate);
  $('phase4b1Giveback').textContent = maybePct(dashboard.giveback_rate);
  $('phase4b1BeTarget').textContent = dashboard.BE_then_target_rate === null || dashboard.BE_then_target_rate === undefined ? 'N/A' : maybePct(dashboard.BE_then_target_rate);
  $('phase4b1Classifier').textContent = maybePct(dashboard.direction_classifier_accuracy);
  $('phase4b1Structure').textContent = maybeR(dashboard.structure_confirmed_expectancy);
  $('phase4b1LossSource').textContent = dashboard.current_biggest_loss_source || 'UNKNOWN';
  $('phase4b1Badge').textContent = dashboard.status || 'NOT GENERATED';
  $('phase4b1Badge').className = `badge ${dashboard.status === 'GENERATED' ? 'warn' : ''}`;
}

async function refreshPhase4b2Prospective() {
  const payload = await json('/research/phase-4b2/status');
  const dashboard = payload.dashboard || {};
  $('phase4b2Parents').textContent = dashboard.parent_events || 0;
  $('phase4b2Qualified').textContent = payload.counts?.qualified_branches || 0;
  const lifecycle = payload.counts?.lifecycle || {};
  $('phase4b2Lifecycle').textContent = Object.entries(lifecycle).map(([key, value]) => `${key}: ${value}`).join(' · ') || '—';
  $('phase4b2Days').textContent = dashboard.unique_trading_days || 0;
  $('phase4b2Stops').textContent = `${maybeR(dashboard.S0_expectancy)} / ${maybeR(dashboard.S1_expectancy)} / ${maybeR(dashboard.S2_expectancy)} / ${maybeR(dashboard.S3_expectancy)}`;
  $('phase4b2BestStop').textContent = dashboard.best_stop_branch || '—';
  $('phase4b2Mgmt').textContent = `${maybeR(dashboard.M0_expectancy)} / ${maybeR(dashboard.M1_expectancy)} / ${maybeR(dashboard.M2_expectancy)} / ${maybeR(dashboard.M3_expectancy)} / ${maybeR(dashboard.M4_expectancy)}`;
  $('phase4b2BestMgmt').textContent = dashboard.best_management_branch || '—';
  $('phase4b2P0').textContent = maybeR(dashboard.P0_expectancy);
  $('phase4b2P4').textContent = maybeR(dashboard.P4_expectancy);
  $('phase4b2P4Delta').textContent = maybeR(dashboard.P4_vs_P0_expectancy_delta);
  $('phase4b2BadStop').textContent = dashboard.BAD_STOP_causality_status || 'INSUFFICIENT_FORWARD_SAMPLE';
  $('phase4b2ProfitStatus').textContent = dashboard.profit_protection_status || 'INSUFFICIENT_FORWARD_SAMPLE';
  $('phase4b2OptionsStatus').textContent = dashboard.options_value_status || 'INSUFFICIENT_FORWARD_SAMPLE';
  $('phase4b2Badge').textContent = dashboard.milestone_status || 'INSTRUMENTATION_PENDING';
  $('phase4b2Badge').className = `badge ${dashboard.milestone_status === 'PRIMARY_DECISION_POINT_READY' ? 'good' : 'warn'}`;
}

async function runScan(fixture) {
  const button = fixture ? $('demoButton') : $('scanButton');
  button.disabled = true;
  button.textContent = 'Scanning…';
  try {
    const data = await json('/scanner/options-structure/run-once', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({tickers: [$('ticker').value], fixture, open_paper: !fixture})});
    const result = data.results[0];
    loadTicker(result);
    if (!result.setup) {
      $('signalBadge').textContent = (result.outcome || 'NO SETUP').toUpperCase().replaceAll('_', ' ');
      $('signalBadge').className = 'badge warn';
      $('spot').textContent = (result.reasons || []).join(' · ') || 'No reclaim on the latest closed candle.';
    }
    const levels = await json(`/ticker/${$('ticker').value}/levels`);
    const call = levels.find(item => item.level_type === 'CALL_WALL');
    const put = levels.find(item => item.level_type === 'PUT_WALL');
    $('callWall').textContent = call ? money(call.price) : '—';
    $('putWall').textContent = put ? money(put.price) : '—';
    await Promise.all([refreshObservation(), refreshDaemon(), refreshWatchlist(), refreshPhase2d(), refreshFreshness(), refreshPaperStatus(), refreshTradeManagementResearch(), refreshManagementAB(), refreshEdgeDiscovery(), refreshForwardEdgeValidation(), refreshPhase4aResearch(), refreshPhase4b1EdgeDecomposition(), refreshPhase4b2Prospective()]);
  } catch (error) {
    $('spot').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = fixture ? 'Run demo' : 'Run real-data scan';
  }
}

async function init() {
  $('scanButton').onclick = () => runScan(false);
  $('demoButton').onclick = () => runScan(true);
  $('ticker').onchange = () => {$('selectedTicker').textContent = $('ticker').value;};
  await refreshWatchlist();
  const [sources, events, performance, config] = await Promise.all([
    json('/sources/status'), json('/macro/events'),
    json('/performance/summary?mode=free_validation_paper'), json('/config/status')]);
  const ready = sources.filter(source => source.configured && source.enabled && source.free_validation_eligible).length;
  $('providerReadiness').textContent = `${ready} FREE`;
  $('sources').innerHTML = sources.map(source => `<div class="row"><span><i class="dot ${source.configured ? 'on' : ''}"></i>${source.name}</span><small>${source.configured ? (source.production_eligible ? 'Production ready' : source.free_validation_eligible ? 'Free Validation' : 'Shadow only') : 'not configured'}</small></div>`).join('');
  $('configStatus').textContent = `${config.runtime_mode} · ${config.watchlist.configured_symbols} symbols · live auto disabled · macro calendar ${config.macro_calendar_production_eligible ? 'approved' : 'not approved'}`;
  $('events').innerHTML = events.slice(0, 4).map(event => `<div class="row"><span>${event.event_name}</span><small>${new Date(event.event_time_utc).toLocaleDateString()}</small></div>`).join('') || '<p class="muted">No approved events loaded</p>';
  $('sampleSize').textContent = performance.sample_size;
  $('expectancy').textContent = `${performance.expectancy_R}R`;
  $('winRate').textContent = `${Math.round(performance.win_rate * 100)}%`;
  $('drawdown').textContent = `${performance.max_drawdown_R}R`;
  $('exportButton').onclick = async () => {
    const data = await json('/exports/research', {method: 'POST'});
    $('exportStatus').textContent = `Exported ${Object.keys(data).length} files to the isolated data folder.`;
  };
  await Promise.all([refreshObservation(), refreshDaemon(), refreshPhase2d(), refreshFreshness(), refreshPaperStatus(), refreshTradeManagementResearch(), refreshManagementAB(), refreshEdgeDiscovery(), refreshForwardEdgeValidation(), refreshPhase4aResearch(), refreshPhase4b1EdgeDecomposition(), refreshPhase4b2Prospective()]);
}

init().catch(error => {$('spot').textContent = error.message;});
