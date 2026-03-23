# Migration note:
# Trade suggestions now carry planning_only/execution_allowed tags for OFFHOURS handling.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

@dataclass(frozen=True)
class Trade:
    trade_id: str
    timestamp: datetime
    symbol: str
    instrument: str
    instrument_token: int | None
    strike: int
    expiry: str
    side: str              # BUY / SELL
    entry_price: float
    stop_loss: float
    target: float
    qty: int
    capital_at_risk: float
    expected_slippage: float
    confidence: float
    strategy: str
    regime: str
    tier: str = "MAIN"
    day_type: str = "UNKNOWN"
    regime_confidence: float | None = None
    day_confidence: float | None = None
    orb_bias: str | None = None
    entry_condition: str | None = None   # e.g., BUY_ABOVE / SELL_BELOW
    entry_ref_price: float | None = None # original ask/ltp used before trigger
    signal_price: float | None = None
    execution_entry: float | None = None
    execution_entry_source: str | None = None
    execution_entry_status: str | None = None
    display_entry: float | None = None
    display_entry_source: str | None = None
    display_entry_status: str | None = None
    entry_display_status: str | None = None
    entry_reason: str | None = None
    entry_clear_reason: str | None = None
    entry_block_code: str | None = None
    entry_price_source: str | None = None
    expected_entry_source: str | None = None
    entry_price_proxy: float | None = None
    current_ltp: float | None = None
    suggested_entry: float | None = None
    expected_entry: float | None = None
    fill_entry: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    mark_price: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    price_source: str | None = None
    price_age_sec: float | None = None
    quote_age_sec: float | None = None
    entry_status: str | None = None
    status: str | None = None
    activated_ts: str | None = None
    activation_price: float | None = None
    current_ltp_ts: float | None = None
    pnl_points: float | None = None
    pnl_cash: float | None = None
    activation_reason: str | None = None
    invalidation_reason: str | None = None
    best_price_seen: float | None = None
    best_price_ts: float | None = None
    current_sl: float | None = None
    current_tp: float | None = None
    exit_intel_phase: str | None = None
    stall_counter: int | None = None
    last_action_ts: float | None = None
    reason_codes: list[str] = field(default_factory=list)
    opt_ltp: float | None = None
    opt_bid: float | None = None
    opt_ask: float | None = None
    volume: float | None = None
    current_volume: float | None = None
    oi: float | None = None
    oi_change: float | None = None
    quote_ok: bool = True
    trade_score: float | None = None
    trade_alignment: float | None = None
    trade_score_detail: dict | None = None
    model_type: str | None = None
    model_version: str | None = None
    shadow_model_version: str | None = None
    shadow_confidence: float | None = None
    alpha_confidence: float | None = None
    alpha_uncertainty: float | None = None
    size_mult: float = 1.0
    option_type: str | None = None
    underlying: str | None = None
    instrument_type: str | None = None
    right: str | None = None
    instrument_id: str | None = None
    tradingsymbol: str | None = None
    expiry_date: str | None = None
    qty_lots: int | None = None
    qty_units: int | None = None
    validity_sec: int | None = None
    tradable: bool = True
    tradable_reasons_blocking: list[str] = field(default_factory=list)
    source_flags: dict = field(default_factory=dict)
    planning_only: bool = False
    execution_allowed: bool = True
    reason: str | None = None
    stop_distance: float | None = None
    underlying_spot: float | None = None
    spot_source: str | None = None
    option_ltp_source: str | None = None
    option_ltp_timestamp: float | None = None
    chain_source: str | None = None
    direction: str | None = None
    candidate_type: str | None = None
    strategy_family: str | None = None
    setup_variant: str | None = None
    candidate_status: str | None = None
    global_confidence: float | None = None
    builder_confidence: float | None = None
    permission_confidence: float | None = None
    gating_base_confidence: float | None = None
    gating_final_confidence: float | None = None
    sizing_confluence_score: float | None = None
    rank_score: float | None = None
    setup_strength: float | None = None
    regime_fit: float | None = None
    liquidity_score: float | None = None
    spread_score: float | None = None
    rr_score: float | None = None
    timing_score: float | None = None
    penalty_score: float | None = None
    score_breakdown: dict = field(default_factory=dict)
    penalty_reasons: list[str] = field(default_factory=list)
    score_inputs_used: dict = field(default_factory=dict)
    opportunity_score: float | None = None
    opportunity_rank: int | None = None
    rank_global: int | None = None
    rank_within_symbol: int | None = None
    opportunity_bucket: str | None = None
    selected_for_execution: bool | None = None
    selection_reason: str | None = None
    size_multiplier_reason: str | None = None
    opportunity_size_multiplier: float | None = None
    threshold_base: float | None = None
    threshold_effective: float | None = None
    threshold_adjustment_reason: str | None = None
    spread_penalty: float | None = None
    executable_price_estimate: float | None = None
    execution_ok: bool | None = None
    order_policy: str | None = None
    order_policy_reason: str | None = None
    slot_id: str | None = None
    allocation_reason: str | None = None
    allocation_score: float | None = None
    capital_assigned: float | None = None
    size_multiplier_effective: float | None = None
    portfolio_optimization_selected: bool | None = None
    portfolio_optimization_reason: str | None = None
    portfolio_optimization_score: float | None = None
    portfolio_optimization_penalty: float | None = None
    portfolio_optimization_penalty_reason: str | None = None
    sizing_reason: str | None = None
    ml_proba_input: float | None = None
    confluence_input: float | None = None
    ml_proba_source: str | None = None
    confluence_source: str | None = None
    confidence_size_multiplier: float | None = None
    final_qty: int | None = None
    permission: str | None = None
    permission_reason: str | None = None
    countertrend: bool | None = None
    raw_signal_confidence: float | None = None
    confidence_model_raw: float | None = None
    confidence_model_component: float | None = None
    confidence_micro_component: float | None = None
    confidence_micro_blend_method: str | None = None
    confidence_after_micro: float | None = None
    confidence_after_alpha: float | None = None
    confidence_after_latency: float | None = None
    confidence_before_soft_veto: float | None = None
    confidence_after_soft_veto: float | None = None
    confidence_penalty_soft_veto_total: float | None = None
    confidence_penalty_soft_veto_reasons: list[str] = field(default_factory=list)
    confidence_gate_threshold: float | None = None
    confidence_raw_gate_threshold: float | None = None
    confidence_final_gate_threshold: float | None = None
    confidence_rejection_stage: str | None = None
    confidence_base: float | None = None
    confidence_penalty_total: float | None = None
    confidence_penalty_reasons: list[str] = field(default_factory=list)
    trade_key: str | None = None
    snapshot_id: str | None = None
    trade_status: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    update_count: int | None = None
    trade_lifecycle_state: str | None = None
    trade_lifecycle_reason: str | None = None
    trade_lifecycle_ts: str | None = None
    trade_lifecycle_history: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.entry_display_status is None:
            object.__setattr__(self, "entry_display_status", self.display_entry_status)
        if self.entry_block_code is None:
            block_code = None
            if self.entry_clear_reason:
                block_code = str(self.entry_clear_reason).strip().lower() or None
            object.__setattr__(self, "entry_block_code", block_code)
        if self.builder_confidence is None:
            object.__setattr__(self, "builder_confidence", self.confidence)
        if self.gating_base_confidence is None:
            base_confidence = self.confidence_base
            if base_confidence is None:
                base_confidence = self.builder_confidence
            object.__setattr__(self, "gating_base_confidence", base_confidence)
        if self.gating_final_confidence is None:
            final_confidence = self.confidence_after_soft_veto
            if final_confidence is None:
                final_confidence = self.confidence
            object.__setattr__(self, "gating_final_confidence", final_confidence)
        if self.permission_confidence is None:
            object.__setattr__(self, "permission_confidence", self.global_confidence)
        if self.sizing_confluence_score is None and isinstance(self.trade_score_detail, dict):
            object.__setattr__(self, "sizing_confluence_score", self.trade_score_detail.get("confluence_score"))
        try:
            from core.trade_state_machine import build_trade_lifecycle_snapshot

            lifecycle_snapshot = build_trade_lifecycle_snapshot(self)
            if self.trade_lifecycle_state is None:
                object.__setattr__(self, "trade_lifecycle_state", lifecycle_snapshot.get("trade_lifecycle_state"))
            if self.trade_lifecycle_reason is None:
                object.__setattr__(self, "trade_lifecycle_reason", lifecycle_snapshot.get("trade_lifecycle_reason"))
            if self.trade_lifecycle_ts is None:
                object.__setattr__(self, "trade_lifecycle_ts", lifecycle_snapshot.get("trade_lifecycle_ts"))
            if not self.trade_lifecycle_history:
                object.__setattr__(self, "trade_lifecycle_history", lifecycle_snapshot.get("trade_lifecycle_history") or [])
        except Exception:
            pass
        if self.stop_distance is not None:
            return
        try:
            distance = abs(float(self.entry_price) - float(self.stop_loss))
        except (TypeError, ValueError):
            distance = None
        if distance is not None and distance > 0:
            object.__setattr__(self, "stop_distance", distance)


@dataclass
class TradeIntent:
    trace_id: str
    desk_id: str
    timestamp_epoch: float
    underlying: str
    instrument_type: str
    expiry: str | None
    strike: int | float | None
    right: str | None
    instrument_id: str | None
    side: str
    entry_type: str
    entry_price: float
    sl_price: float
    target_price: float
    qty_lots: int
    qty_units: int
    validity_sec: int
    tradable: bool = False
    tradable_reasons_blocking: list[str] = field(default_factory=list)
    source_flags: dict = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)

    def build_instrument_id(self) -> Optional[str]:
        return build_instrument_id(
            self.underlying,
            self.instrument_type,
            self.expiry,
            self.strike,
            self.right,
        )

    def validate_prices(self) -> Tuple[bool, str]:
        if self.entry_price is None or self.entry_price <= 0:
            return False, "invalid_entry_price"
        if self.sl_price is None or self.sl_price <= 0:
            return False, "invalid_stop_loss"
        if self.target_price is None or self.target_price <= 0:
            return False, "invalid_target"
        if self.side == "BUY":
            if self.sl_price >= self.entry_price:
                return False, "stop_above_entry"
            if self.target_price <= self.entry_price:
                return False, "target_below_entry"
        if self.side == "SELL":
            if self.sl_price <= self.entry_price:
                return False, "stop_below_entry"
            if self.target_price >= self.entry_price:
                return False, "target_above_entry"
        return True, "ok"

    def is_actionable(self) -> Tuple[bool, str]:
        if self.tradable is False:
            return False, "non_tradable"
        if not self.trace_id:
            return False, "missing_trace_id"
        if not self.desk_id:
            return False, "missing_desk_id"
        if self.side not in ("BUY", "SELL"):
            return False, "invalid_side"
        if self.entry_type not in ("LIMIT", "MARKET"):
            return False, "invalid_entry_type"
        if self.qty_lots <= 0:
            return False, "invalid_qty_lots"
        if self.qty_units <= 0:
            return False, "invalid_qty_units"
        if self.validity_sec <= 0:
            return False, "invalid_validity_sec"
        ok_identity, reason_identity = validate_trade_identity(
            self.underlying,
            self.instrument_type,
            self.expiry,
            self.strike,
            self.right,
        )
        if not ok_identity:
            return False, reason_identity
        current_id = self.instrument_id or self.build_instrument_id()
        if not current_id:
            return False, "missing_instrument_id"
        ok_price, reason_price = self.validate_prices()
        if not ok_price:
            return False, reason_price
        return True, "ok"


def build_instrument_id(
    underlying: str | None,
    instrument_type: str | None,
    expiry: str | None,
    strike: int | float | None,
    right: str | None,
) -> Optional[str]:
    if not underlying or not instrument_type:
        return None
    instrument_type = instrument_type.upper()
    if instrument_type == "OPT":
        if not expiry or strike is None or not right:
            return None
        return f"{underlying}|{expiry}|{strike}|{right}"
    if instrument_type == "FUT":
        if not expiry:
            return None
        return f"{underlying}|{expiry}|FUT"
    if instrument_type == "INDEX":
        return f"{underlying}|INDEX"
    return None


def validate_trade_identity(
    underlying: str | None,
    instrument_type: str | None,
    expiry: str | None,
    strike: int | float | None,
    right: str | None,
) -> Tuple[bool, str]:
    if not underlying:
        return False, "missing_underlying"
    if not instrument_type:
        return False, "missing_instrument_type"
    instrument_type = instrument_type.upper()
    if instrument_type == "OPT":
        if not expiry:
            return False, "missing_expiry"
        if strike is None:
            return False, "missing_strike"
        if right not in ("CE", "PE"):
            return False, "missing_right"
    if instrument_type == "FUT" and not expiry:
        return False, "missing_expiry"
    return True, "ok"
