from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class Mode(StrEnum):
    RESEARCH = "research_scan"
    SHADOW = "shadow_paper"
    FREE_VALIDATION = "free_validation_paper"
    PRODUCTION = "production_paper"
    LIVE_ASSISTED = "live_assisted"


class SetupType(StrEnum):
    LEVEL_RECLAIM_LONG = "LEVEL_RECLAIM_LONG"
    LEVEL_RECLAIM_SHORT = "LEVEL_RECLAIM_SHORT"


class Bar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    timeframe: str = "5m"
    bar_start_utc: datetime
    bar_end_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    atr: float
    relative_volume: float = 1.0
    closed: bool = True
    source: str = "unknown"
    source_timestamp_utc: datetime | None = None
    ingestion_timestamp_utc: datetime = Field(default_factory=utc_now)
    source_freshness_seconds: float = 0
    confidence_score: float = Field(default=0.5, ge=0, le=1)
    raw_payload_reference: str | None = None

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, value: str) -> str:
        return value.upper().strip()


class TickerState(BaseModel):
    ticker: str
    timestamp_utc: datetime
    source: str
    spot_price: float
    bid: float
    ask: float
    last: float
    spread_bps: float
    volume_today: float = 0
    relative_volume: float = 1.0
    average_daily_volume: float = 0
    ticker_class: str = "unknown"
    trading_session: str = "regular"
    is_halted: bool = False
    source_freshness_seconds: float = 0
    ingestion_timestamp_utc: datetime = Field(default_factory=utc_now)
    confidence_score: float = Field(default=0.5, ge=0, le=1)
    raw_payload_reference: str | None = None


class Level(BaseModel):
    level_id: str = Field(default_factory=lambda: new_id("lvl"))
    ticker: str
    level_type: str
    price: float
    zone_low: float
    zone_high: float
    known_at_utc: datetime
    source: str
    strength_score: float = 0.5
    source_count: int = 1
    source_agreement_score: float = 1.0
    freshness_score: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GexMap(BaseModel):
    ticker: str
    source: str
    source_timestamp_utc: datetime
    ingestion_timestamp_utc: datetime = Field(default_factory=utc_now)
    spot: float
    gamma_flip: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    max_pain: float | None = None
    expected_move: float | None = None
    atm_iv: float | None = None
    gamma_regime: str = "unknown"
    strikes: list[dict[str, float]] = Field(default_factory=list)
    oi_nodes: list[float] = Field(default_factory=list)
    greeks_summary: dict[str, float] = Field(default_factory=dict)
    field_coverage: dict[str, float] = Field(default_factory=dict)
    missing_required_fields: list[str] = Field(default_factory=list)
    free_validation_complete: bool = False
    raw_payload_reference: str | None = None
    freshness_seconds: float = 0
    staleness_flag: bool = False
    source_conflict_flag: bool = False
    confidence_score: float = Field(default=0.5, ge=0, le=1)
    required_fields_complete: bool = True


class MacroEvent(BaseModel):
    event_id: str
    event_name: str
    event_type: str
    event_time_utc: datetime
    importance: str
    scope: str = "market"
    tickers: list[str] = Field(default_factory=list)
    block_before_minutes: int | None = None
    block_after_minutes: int | None = None
    notes: str = ""
    manually_verified: bool = False
    calendar_approved: bool = False
    source_note: str = ""


class GuardStatus(BaseModel):
    ticker: str
    evaluated_at_utc: datetime
    blocked: bool
    event_name: str | None = None
    event_time_utc: datetime | None = None
    minutes_to_event: float | None = None
    minutes_since_event: float | None = None
    macro_event_proximity_flag: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    macro_unknown: bool = False
    calendar_approved: bool = False


class FeatureSet(BaseModel):
    dealer_positioning: float | None = Field(default=None, ge=0, le=1)
    options_flow: float | None = Field(default=None, ge=0, le=1)
    oi_confirmation: float | None = Field(default=None, ge=0, le=1)
    big_trades_dark_pool: float | None = Field(default=None, ge=0, le=1)
    price_structure: float | None = Field(default=None, ge=0, le=1)
    volatility_liquidity: float | None = Field(default=None, ge=0, le=1)
    data_quality_event_guard: float | None = Field(default=None, ge=0, le=1)
    flow_direction: str = "unknown"
    retest_confirmed: bool = False
    volume_expansion: bool = False
    data_staleness_flag: bool = False
    source_conflict_flag: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class ScoreResult(BaseModel):
    total: float
    raw_score: float
    adjusted_score: float
    confidence_score: float = Field(ge=0, le=1)
    missing_components: list[str] = Field(default_factory=list)
    data_quality_tier: str = "FULL"
    breakdown: dict[str, float | None]
    raw_components: dict[str, float | None]
    score_model_version: str
    score_weight_set_id: str


class EligibilityContext(BaseModel):
    real_data: bool
    synthetic_present: bool = False
    supported_ticker: bool
    session_valid: bool
    free_validation_session_valid: bool | None = None
    session_name: str
    macro_guard_evaluated: bool
    required_fields_complete: bool
    core_fields_complete: bool = False
    price_provider: str
    structure_provider: str
    price_provider_production_eligible: bool
    structure_provider_production_eligible: bool
    price_provider_free_validation_eligible: bool = False
    structure_provider_free_validation_eligible: bool = False
    price_freshness_seconds: float
    structure_freshness_seconds: float
    macro_calendar_production_eligible: bool = False
    limited_data: bool = False
    unofficial_source: bool = False
    production_grade: bool = False
    gamma_grid_missing: bool = False
    oi_unavailable: bool = False
    greeks_unavailable: bool = False
    confidence_penalty_applied: bool = False
    macro_unknown: bool = False
    missing_components: list[str] = Field(default_factory=list)
    raw_payload_references: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.5, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class ScanInput(BaseModel):
    ticker_state: TickerState
    level: Level
    previous_bar: Bar
    confirmation_bar: Bar
    features: FeatureSet
    target_nodes: list[float]
    guard: GuardStatus | None = None
    source_mode: str = "MANUAL"
    eligibility: EligibilityContext | None = None


class TradePlan(BaseModel):
    entry_zone_low: float
    entry_zone_high: float
    planned_entry: float
    stop_initial: float
    targets: list[float]
    primary_rr: float
    shares: int
    risk_dollars: float
    invalidation_logic: str


class SetupEvent(BaseModel):
    setup_event_id: str = Field(default_factory=lambda: new_id("setup"))
    ticker: str
    setup_type: SetupType
    side: Side
    level_id: str
    level_type: str
    created_at_utc: datetime = Field(default_factory=utc_now)
    score: ScoreResult
    trade_plan: TradePlan | None = None
    production_paper_allowed: bool = False
    free_validation_paper_allowed: bool = False
    shadow_paper_allowed: bool = True
    blocking_reasons: list[str] = Field(default_factory=list)
    free_validation_blocking_reasons: list[str] = Field(default_factory=list)
    recommended_mode: Mode = Mode.SHADOW
    reason: list[str] = Field(default_factory=list)
    config_version: str
    source_mode: str
    signal_snapshot: dict[str, Any]


class PaperTrade(BaseModel):
    trade_id: str = Field(default_factory=lambda: new_id("trade"))
    setup_event_id: str
    ticker: str
    setup_type: str
    side: Side
    mode: Mode
    created_at_utc: datetime = Field(default_factory=utc_now)
    opened_at_utc: datetime | None = None
    tp1_at_utc: datetime | None = None
    closed_at_utc: datetime | None = None
    entry_type: str = "market_sim"
    entry_zone_low: float
    entry_zone_high: float
    planned_entry: float
    actual_fill_price: float | None = None
    stop_initial: float
    stop_current: float
    targets: list[float]
    shares: int
    remaining_shares: int
    risk_dollars: float
    status: str = "pending"
    bars_pending: int = 0
    realized_r: float = 0
    mfe_r: float = 0
    mae_r: float = 0
    fees: float = 0
    slippage: float = 0
    exit_reason: str | None = None
    score_total: float
    score_breakdown: dict[str, float | None]
    score_model_version: str
    config_version: str
    macro_event_flags: dict[str, Any] = Field(default_factory=dict)
    variant_id: str | None = None


class ScanRequest(BaseModel):
    tickers: list[str] | None = None
    fixture: bool = True
    open_paper: bool = False


class ObservationRequest(BaseModel):
    tickers: list[str] | None = None
    cycles: int = Field(default=1, ge=1, le=1000)
    interval_seconds: int = Field(default=60, ge=0, le=3600)
    open_paper: bool = True
    include_free_fallback: bool = True
    mode: str = "free-validation"
    rth_only: bool = False
    target_scans: int | None = Field(default=None, ge=1, le=10000)


class ReplayRequest(BaseModel):
    snapshots: list[ScanInput] = Field(default_factory=list)
    open_paper: bool = False
