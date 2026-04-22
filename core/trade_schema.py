# Migration note:
# Trade suggestions now carry planning_only/execution_allowed tags for OFFHOURS handling.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple


def _safe_float(value) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _normalize_code_list(value) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    elif value in (None, "", "None"):
        raw_items = []
    else:
        raw_items = [value]
    out: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


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
    requested_strike: float | None = None
    resolved_strike: float | None = None
    requested_expiry: str | None = None
    resolved_expiry: str | None = None
    contract_exact_match: bool | None = None
    resolution_mode: str | None = None
    resolution_penalty: float | None = None
    fallback_used: bool | None = None
    fallback_class: str | None = None
    fallback_reason: str | None = None
    fallback_execution_policy: str | None = None
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
    direction_family: str | None = None
    family_rank: int | None = None
    family_blocker: str | None = None
    family_strength: float | None = None
    family_allowed_in_context: bool | None = None
    family_gate_reason: str | None = None
    family_gate_override_applied: bool | None = None
    setup_variant: str | None = None
    candidate_status: str | None = None
    lifecycle_stage: str | None = None
    global_confidence: float | None = None
    builder_confidence: float | None = None
    permission_confidence: float | None = None
    gating_base_confidence: float | None = None
    gating_final_confidence: float | None = None
    confidence_shadow: float | None = None
    sizing_confluence_score: float | None = None
    rank_score: float | None = None
    setup_strength: float | None = None
    setup_score: float | None = None
    trigger_score: float | None = None
    entry_quality_score: float | None = None
    entry_quality_reason: str | None = None
    overextension_score: float | None = None
    overextension_penalty: float | None = None
    entry_distance_to_invalidation: float | None = None
    session_mode: str | None = None
    strategy_regime_mode: str | None = None
    session_entry_penalty: float | None = None
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
    opportunity_score_shadow: float | None = None
    final_score: float | None = None
    signal_score: float | None = None
    execution_score: float | None = None
    priority_score: float | None = None
    priority_weight_signal: float | None = None
    priority_weight_execution: float | None = None
    family_feedback_adjustment: float | None = None
    family_feedback_confidence: float | None = None
    family_feedback_applied: bool | None = None
    family_learning_adjustment: float | None = None
    family_cap_effective: int | None = None
    family_cap_reason: str | None = None
    family_consensus_score: float | None = None
    family_consensus_components: dict = field(default_factory=dict)
    family_survival_score: float | None = None
    family_survival_components: dict = field(default_factory=dict)
    family_survived: bool | None = None
    family_reject_reason: str | None = None
    expectancy_score: float | None = None
    family_learning_state_generated_at: str | None = None
    family_learning_state_version: int | None = None
    strategy_weight_adjustment: float | None = None
    strategy_weight_confidence: float | None = None
    strategy_weight_applied: bool | None = None
    strategy_weight_state_generated_at: str | None = None
    strategy_weight_state_version: int | None = None
    adaptive_threshold_adjustment: float | None = None
    adaptive_threshold_impact_score: float | None = None
    adaptive_threshold_applied: bool | None = None
    adaptive_threshold_key: str | None = None
    risk_budget_ok: bool | None = None
    risk_budget_reason: str | None = None
    position_size_estimate: int | None = None
    portfolio_heat_score: float | None = None
    correlation_penalty: float | None = None
    exposure_blocker: str | None = None
    daily_kill_switch_active: bool | None = None
    regime_failure_throttle: float | None = None
    family_failure_throttle: float | None = None
    risk_learning_adjustment: float | None = None
    risk_learning_confidence: float | None = None
    rejected_at_stage: str | None = None
    rejection_reason_code: str | None = None
    rejection_bucket: str | None = None
    rejection_severity: str | None = None
    stage_authority_warning: bool | None = None
    trade_density_limit_applied: bool | None = None
    density_policy_name: str | None = None
    density_reject_reason: str | None = None
    raw_candidate_count: int | None = None
    surviving_candidate_count: int | None = None
    survival_rate: float | None = None
    executable_rate: float | None = None
    advisory_rate: float | None = None
    no_trade_rate: float | None = None
    top_family_share: float | None = None
    starvation_flag: bool | None = None
    starvation_reason: str | None = None
    warning_engine_too_timid: bool | None = None
    warning_filtering_without_edge_improvement: bool | None = None
    warning_family_starvation: bool | None = None
    warning_threshold_cluster: bool | None = None
    rejection_impact_warning: str | None = None
    starvation_warning: bool | None = None
    edge_improved_flag: bool | None = None
    filtering_without_edge_flag: bool | None = None
    top_damaging_gate_rank: int | None = None
    recommended_threshold_delta: float | None = None
    gate_protected_flag: bool | None = None
    triage_recommendation: str | None = None
    edge_preserve_flag: bool | None = None
    effective_session_policy: dict = field(default_factory=dict)
    effective_regime_policy: dict = field(default_factory=dict)
    effective_risk_policy: dict = field(default_factory=dict)
    effective_family_risk_profile: dict = field(default_factory=dict)
    risk_profile_override_applied: bool | None = None
    effective_family_survival_policy: dict = field(default_factory=dict)
    aggressiveness_mode: str | None = None
    aggressiveness_adjustment: float | None = None
    aggressiveness_adjustment_applied: bool | None = None
    opportunity_rank: int | None = None
    opportunity_rank_shadow: int | None = None
    rank_global: int | None = None
    rank_within_symbol: int | None = None
    opportunity_bucket: str | None = None
    candidate_class: str | None = None
    market_mode: str | None = None
    data_state: str | None = None
    data_confidence: float | None = None
    spread_stability_score: float | None = None
    book_freshness_score: float | None = None
    quote_completeness_score: float | None = None
    quote_consistency_score: float | None = None
    quote_completeness: str | None = None
    quote_consistency_ok: bool | None = None
    ltp_age_sec: float | None = None
    bid_age_sec: float | None = None
    ask_age_sec: float | None = None
    chain_snapshot_age_sec: float | None = None
    spread_source: str | None = None
    liquidity_validation_mode: str | None = None
    fresh_quote_ok: bool | None = None
    liquidity_ok: bool | None = None
    spread_ok: bool | None = None
    primary_blocker: str | None = None
    truth_allows_execution: bool | None = None
    class_blocks_execution: bool | None = None
    debug_blocks_execution: bool | None = None
    selected_for_execution: bool | None = None
    selected_for_execution_shadow: bool | None = None
    selection_reason: str | None = None
    selector_outcome: str | None = None
    selection_probability: float | None = None
    simulation_outcome: str | None = None
    simulation_fill_status: str | None = None
    simulation_fill_qty: int | None = None
    mfe: float | None = None
    mae: float | None = None
    simulated_pnl: float | None = None
    would_have_worked: bool | None = None
    rejection_saved_loss: bool | None = None
    rejection_missed_win: bool | None = None
    realized_r_multiple: float | None = None
    stop_hit_before_target: bool | None = None
    risk_plan_respected: bool | None = None
    size_multiplier_reason: str | None = None
    opportunity_size_multiplier: float | None = None
    threshold_base: float | None = None
    threshold_effective: float | None = None
    threshold_adjustment_reason: str | None = None
    expected_slippage_bps: float | None = None
    spread_penalty: float | None = None
    slippage_risk: float | None = None
    depth_score: float | None = None
    fill_probability: float | None = None
    execution_quality_score: float | None = None
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
    final_action: str | None = None
    readiness: str | None = None
    execution_status: str | None = None
    gates_failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decision_trace: dict = field(default_factory=dict)
    countertrend: bool | None = None
    raw_signal_confidence: float | None = None
    confidence_raw_canonical: float | None = None
    confidence_stage_trace: dict = field(default_factory=dict)
    confidence_model_raw: float | None = None
    confidence_model_component: float | None = None
    confidence_micro_component: float | None = None
    confidence_micro_blend_method: str | None = None
    confidence_after_micro: float | None = None
    confidence_after_alpha: float | None = None
    confidence_after_latency: float | None = None
    confidence_before_soft_veto: float | None = None
    confidence_after_soft_veto: float | None = None
    confidence_after_time_decay: float | None = None
    confidence_time_decay_factor: float | None = None
    confidence_age_seconds: float | None = None
    confidence_market_velocity: float | None = None
    confidence_age_factor: float | None = None
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
        source_flags = dict(self.source_flags or {})
        for list_key in ("warning_codes", "soft_veto_codes", "gates_failed", "advisory_flags"):
            if list_key in source_flags:
                source_flags[list_key] = _normalize_code_list(source_flags.get(list_key))
        if source_flags != dict(self.source_flags or {}):
            object.__setattr__(self, "source_flags", source_flags)
        if self.confidence_raw_canonical is None:
            canonical_raw = None
            for candidate in (
                self.confidence_model_raw,
                self.confidence_before_soft_veto,
                self.confidence_after_latency,
                self.confidence_after_alpha,
                self.confidence_after_micro,
                self.confidence_base,
                self.builder_confidence,
                self.confidence,
            ):
                if candidate is not None:
                    canonical_raw = candidate
                    break
            object.__setattr__(self, "confidence_raw_canonical", canonical_raw)
        existing_stage_trace = dict(self.confidence_stage_trace or {})
        final_confidence_stage = None
        for candidate in (
            self.confidence_after_time_decay,
            _safe_float(existing_stage_trace.get("after_time_decay")),
            self.gating_final_confidence,
            self.confidence_after_soft_veto,
            _safe_float(existing_stage_trace.get("after_soft_veto")),
            self.confidence,
        ):
            if candidate is not None:
                final_confidence_stage = candidate
                break
        if self.confidence_after_time_decay is None:
            object.__setattr__(self, "confidence_after_time_decay", final_confidence_stage)
        if self.confidence_time_decay_factor is None:
            decay_factor = _safe_float(existing_stage_trace.get("time_decay_factor"))
            if decay_factor is None:
                decay_factor = 1.0
            object.__setattr__(self, "confidence_time_decay_factor", decay_factor)
        if self.confidence_age_seconds is None:
            age_seconds = _safe_float(existing_stage_trace.get("age_seconds"))
            if age_seconds is None:
                age_seconds = _safe_float(self.quote_age_sec)
            if age_seconds is None:
                age_seconds = _safe_float(self.price_age_sec)
            object.__setattr__(self, "confidence_age_seconds", age_seconds)
        if self.confidence_market_velocity is None:
            object.__setattr__(self, "confidence_market_velocity", _safe_float(existing_stage_trace.get("market_velocity")))
        if self.confidence_age_factor is None:
            age_factor = _safe_float(existing_stage_trace.get("age_factor"))
            if age_factor is None and self.confidence_age_seconds is not None:
                velocity = _safe_float(self.confidence_market_velocity)
                age_factor = float(self.confidence_age_seconds) / max(float(velocity or 1.0), 1e-6)
            object.__setattr__(self, "confidence_age_factor", age_factor)
        if self.builder_confidence is None:
            object.__setattr__(self, "builder_confidence", final_confidence_stage)
        if self.gating_final_confidence is None:
            object.__setattr__(self, "gating_final_confidence", final_confidence_stage)
        object.__setattr__(
            self,
            "confidence_stage_trace",
            {
                "model_raw": self.confidence_model_raw if self.confidence_model_raw is not None else _safe_float(existing_stage_trace.get("model_raw")),
                "after_micro": self.confidence_after_micro if self.confidence_after_micro is not None else _safe_float(existing_stage_trace.get("after_micro")),
                "after_alpha": self.confidence_after_alpha if self.confidence_after_alpha is not None else _safe_float(existing_stage_trace.get("after_alpha")),
                "after_latency": self.confidence_after_latency if self.confidence_after_latency is not None else _safe_float(existing_stage_trace.get("after_latency")),
                "before_soft_veto": self.confidence_before_soft_veto if self.confidence_before_soft_veto is not None else _safe_float(existing_stage_trace.get("before_soft_veto")),
                "after_soft_veto": self.confidence_after_soft_veto if self.confidence_after_soft_veto is not None else _safe_float(existing_stage_trace.get("after_soft_veto")),
                "after_time_decay": self.confidence_after_time_decay,
                "time_decay_factor": self.confidence_time_decay_factor,
                "age_seconds": self.confidence_age_seconds,
                "market_velocity": self.confidence_market_velocity,
                "age_factor": self.confidence_age_factor,
                "raw_gate_threshold": self.confidence_raw_gate_threshold if self.confidence_raw_gate_threshold is not None else _safe_float(existing_stage_trace.get("raw_gate_threshold")),
                "final_gate_threshold": self.confidence_final_gate_threshold if self.confidence_final_gate_threshold is not None else _safe_float(existing_stage_trace.get("final_gate_threshold")),
                "rejected_at": self.confidence_rejection_stage if self.confidence_rejection_stage is not None else existing_stage_trace.get("rejected_at"),
            },
        )
        if self.entry_display_status is None:
            object.__setattr__(self, "entry_display_status", self.display_entry_status)
        if self.entry_block_code is None:
            block_code = None
            if self.entry_clear_reason:
                block_code = str(self.entry_clear_reason).strip().lower() or None
            object.__setattr__(self, "entry_block_code", block_code)
        if self.gating_base_confidence is None:
            base_confidence = self.confidence_base
            if base_confidence is None:
                base_confidence = self.builder_confidence
            object.__setattr__(self, "gating_base_confidence", base_confidence)
        if self.permission_confidence is None:
            object.__setattr__(self, "permission_confidence", self.global_confidence)
        if bool((self.source_flags or {}).get("fallback_candidate")):
            object.__setattr__(self, "execution_allowed", False)
            object.__setattr__(self, "planning_only", True)
            object.__setattr__(self, "tradable", False)
            object.__setattr__(self, "selected_for_execution", False)
            object.__setattr__(self, "permission", "ADVISORY_ONLY")
            object.__setattr__(self, "final_action", "ADVISORY_ONLY")
            object.__setattr__(self, "execution_status", "advisory_only")
            object.__setattr__(self, "readiness", "ADVISORY_ONLY")
        if self.sizing_confluence_score is None and isinstance(self.trade_score_detail, dict):
            object.__setattr__(self, "sizing_confluence_score", self.trade_score_detail.get("confluence_score"))
        if self.final_score is None and self.opportunity_score is not None:
            object.__setattr__(self, "final_score", self.opportunity_score)
        if self.priority_score is None:
            object.__setattr__(self, "priority_score", self.final_score)
        if self.market_mode is None:
            runtime_mode = None
            if isinstance(self.source_flags, dict):
                runtime_mode = self.source_flags.get("runtime_mode") or self.source_flags.get("market_mode")
            object.__setattr__(self, "market_mode", runtime_mode)
        if self.data_state is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "data_state", self.source_flags.get("data_state"))
        if self.data_confidence is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "data_confidence", self.source_flags.get("data_confidence"))
        if self.spread_stability_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "spread_stability_score", self.source_flags.get("spread_stability_score"))
        if self.book_freshness_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "book_freshness_score", self.source_flags.get("book_freshness_score"))
        if self.quote_completeness_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "quote_completeness_score", self.source_flags.get("quote_completeness_score"))
        if self.quote_consistency_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "quote_consistency_score", self.source_flags.get("quote_consistency_score"))
        if self.quote_completeness is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "quote_completeness", self.source_flags.get("quote_completeness"))
        if self.quote_consistency_ok is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "quote_consistency_ok", self.source_flags.get("quote_consistency_ok"))
        if self.ltp_age_sec is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "ltp_age_sec", self.source_flags.get("ltp_age_sec"))
        if self.bid_age_sec is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "bid_age_sec", self.source_flags.get("bid_age_sec"))
        if self.ask_age_sec is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "ask_age_sec", self.source_flags.get("ask_age_sec"))
        if self.chain_snapshot_age_sec is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "chain_snapshot_age_sec", self.source_flags.get("chain_snapshot_age_sec"))
        if self.spread_source is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "spread_source", self.source_flags.get("spread_source"))
        if self.liquidity_validation_mode is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "liquidity_validation_mode", self.source_flags.get("liquidity_validation_mode"))
        if self.fresh_quote_ok is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "fresh_quote_ok", self.source_flags.get("fresh_quote_ok"))
        if self.liquidity_ok is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "liquidity_ok", self.source_flags.get("liquidity_ok"))
        if self.spread_ok is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "spread_ok", self.source_flags.get("spread_ok"))
        if self.direction_family is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "direction_family", self.source_flags.get("direction_family"))
        if self.family_rank is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_rank", self.source_flags.get("family_rank"))
        if self.family_blocker is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_blocker", self.source_flags.get("family_blocker"))
        if self.family_strength is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_strength", self.source_flags.get("family_strength"))
        if self.family_allowed_in_context is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_allowed_in_context", self.source_flags.get("family_allowed_in_context"))
        if self.family_gate_reason is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_gate_reason", self.source_flags.get("family_gate_reason"))
        if self.family_gate_override_applied is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_gate_override_applied", self.source_flags.get("family_gate_override_applied"))
        if self.signal_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "signal_score", self.source_flags.get("signal_score"))
        if self.execution_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "execution_score", self.source_flags.get("execution_score"))
        if self.setup_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "setup_score", self.source_flags.get("setup_score"))
        if self.trigger_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "trigger_score", self.source_flags.get("trigger_score"))
        if self.entry_quality_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "entry_quality_score", self.source_flags.get("entry_quality_score"))
        if self.entry_quality_reason is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "entry_quality_reason", self.source_flags.get("entry_quality_reason"))
        if self.overextension_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "overextension_score", self.source_flags.get("overextension_score"))
        if self.overextension_penalty is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "overextension_penalty", self.source_flags.get("overextension_penalty"))
        if self.entry_distance_to_invalidation is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "entry_distance_to_invalidation", self.source_flags.get("entry_distance_to_invalidation"))
        if self.session_mode is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "session_mode", self.source_flags.get("session_mode"))
        if self.strategy_regime_mode is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "strategy_regime_mode", self.source_flags.get("strategy_regime_mode"))
        if self.session_entry_penalty is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "session_entry_penalty", self.source_flags.get("session_entry_penalty"))
        if self.priority_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "priority_score", self.source_flags.get("priority_score"))
        if self.priority_weight_signal is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "priority_weight_signal", self.source_flags.get("priority_weight_signal"))
        if self.priority_weight_execution is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "priority_weight_execution", self.source_flags.get("priority_weight_execution"))
        if self.family_feedback_adjustment is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_feedback_adjustment", self.source_flags.get("family_feedback_adjustment"))
        if self.family_feedback_confidence is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_feedback_confidence", self.source_flags.get("family_feedback_confidence"))
        if self.family_feedback_applied is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_feedback_applied", self.source_flags.get("family_feedback_applied"))
        if self.family_learning_adjustment is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_learning_adjustment", self.source_flags.get("family_learning_adjustment"))
        if self.family_cap_effective is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_cap_effective", self.source_flags.get("family_cap_effective"))
        if self.family_cap_reason is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_cap_reason", self.source_flags.get("family_cap_reason"))
        if self.family_consensus_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_consensus_score", self.source_flags.get("family_consensus_score"))
        if not self.family_consensus_components and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_consensus_components", self.source_flags.get("family_consensus_components") or {})
        if self.family_survival_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_survival_score", self.source_flags.get("family_survival_score"))
        if not self.family_survival_components and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_survival_components", self.source_flags.get("family_survival_components") or {})
        if self.family_survived is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_survived", self.source_flags.get("family_survived"))
        if self.family_reject_reason is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_reject_reason", self.source_flags.get("family_reject_reason"))
        if self.expectancy_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "expectancy_score", self.source_flags.get("expectancy_score"))
        if self.family_learning_state_generated_at is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_learning_state_generated_at", self.source_flags.get("family_learning_state_generated_at"))
        if self.family_learning_state_version is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_learning_state_version", self.source_flags.get("family_learning_state_version"))
        if self.strategy_weight_adjustment is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "strategy_weight_adjustment", self.source_flags.get("strategy_weight_adjustment"))
        if self.strategy_weight_confidence is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "strategy_weight_confidence", self.source_flags.get("strategy_weight_confidence"))
        if self.strategy_weight_applied is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "strategy_weight_applied", self.source_flags.get("strategy_weight_applied"))
        if self.strategy_weight_state_generated_at is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "strategy_weight_state_generated_at", self.source_flags.get("strategy_weight_state_generated_at"))
        if self.strategy_weight_state_version is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "strategy_weight_state_version", self.source_flags.get("strategy_weight_state_version"))
        if self.adaptive_threshold_adjustment is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "adaptive_threshold_adjustment", self.source_flags.get("adaptive_threshold_adjustment"))
        if self.adaptive_threshold_impact_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "adaptive_threshold_impact_score", self.source_flags.get("adaptive_threshold_impact_score"))
        if self.adaptive_threshold_applied is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "adaptive_threshold_applied", self.source_flags.get("adaptive_threshold_applied"))
        if self.adaptive_threshold_key is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "adaptive_threshold_key", self.source_flags.get("adaptive_threshold_key"))
        if self.risk_budget_ok is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "risk_budget_ok", self.source_flags.get("risk_budget_ok"))
        if self.risk_budget_reason is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "risk_budget_reason", self.source_flags.get("risk_budget_reason"))
        if self.position_size_estimate is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "position_size_estimate", self.source_flags.get("position_size_estimate"))
        if self.portfolio_heat_score is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "portfolio_heat_score", self.source_flags.get("portfolio_heat_score"))
        if self.correlation_penalty is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "correlation_penalty", self.source_flags.get("correlation_penalty"))
        if self.exposure_blocker is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "exposure_blocker", self.source_flags.get("exposure_blocker"))
        if self.daily_kill_switch_active is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "daily_kill_switch_active", self.source_flags.get("daily_kill_switch_active"))
        if self.regime_failure_throttle is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "regime_failure_throttle", self.source_flags.get("regime_failure_throttle"))
        if self.family_failure_throttle is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "family_failure_throttle", self.source_flags.get("family_failure_throttle"))
        if self.risk_learning_adjustment is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "risk_learning_adjustment", self.source_flags.get("risk_learning_adjustment"))
        if self.risk_learning_confidence is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "risk_learning_confidence", self.source_flags.get("risk_learning_confidence"))
        if self.rejected_at_stage is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "rejected_at_stage", self.source_flags.get("rejected_at_stage"))
        if self.rejection_reason_code is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "rejection_reason_code", self.source_flags.get("rejection_reason_code"))
        if self.rejection_bucket is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "rejection_bucket", self.source_flags.get("rejection_bucket"))
        if self.rejection_severity is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "rejection_severity", self.source_flags.get("rejection_severity"))
        if self.stage_authority_warning is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "stage_authority_warning", self.source_flags.get("stage_authority_warning"))
        if self.trade_density_limit_applied is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "trade_density_limit_applied", self.source_flags.get("trade_density_limit_applied"))
        if self.density_policy_name is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "density_policy_name", self.source_flags.get("density_policy_name"))
        if self.density_reject_reason is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "density_reject_reason", self.source_flags.get("density_reject_reason"))
        if self.raw_candidate_count is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "raw_candidate_count", self.source_flags.get("raw_candidate_count"))
        if self.surviving_candidate_count is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "surviving_candidate_count", self.source_flags.get("surviving_candidate_count"))
        if self.survival_rate is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "survival_rate", self.source_flags.get("survival_rate"))
        if self.executable_rate is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "executable_rate", self.source_flags.get("executable_rate"))
        if self.advisory_rate is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "advisory_rate", self.source_flags.get("advisory_rate"))
        if self.no_trade_rate is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "no_trade_rate", self.source_flags.get("no_trade_rate"))
        if self.top_family_share is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "top_family_share", self.source_flags.get("top_family_share"))
        if self.starvation_flag is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "starvation_flag", self.source_flags.get("starvation_flag"))
        if self.starvation_reason is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "starvation_reason", self.source_flags.get("starvation_reason"))
        if self.warning_engine_too_timid is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "warning_engine_too_timid", self.source_flags.get("warning_engine_too_timid"))
        if self.warning_filtering_without_edge_improvement is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "warning_filtering_without_edge_improvement", self.source_flags.get("warning_filtering_without_edge_improvement"))
        if self.warning_family_starvation is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "warning_family_starvation", self.source_flags.get("warning_family_starvation"))
        if self.warning_threshold_cluster is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "warning_threshold_cluster", self.source_flags.get("warning_threshold_cluster"))
        if self.rejection_impact_warning is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "rejection_impact_warning", self.source_flags.get("rejection_impact_warning"))
        if self.starvation_warning is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "starvation_warning", self.source_flags.get("starvation_warning"))
        if self.edge_improved_flag is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "edge_improved_flag", self.source_flags.get("edge_improved_flag"))
        if self.filtering_without_edge_flag is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "filtering_without_edge_flag", self.source_flags.get("filtering_without_edge_flag"))
        if self.top_damaging_gate_rank is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "top_damaging_gate_rank", self.source_flags.get("top_damaging_gate_rank"))
        if self.recommended_threshold_delta is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "recommended_threshold_delta", self.source_flags.get("recommended_threshold_delta"))
        if self.gate_protected_flag is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "gate_protected_flag", self.source_flags.get("gate_protected_flag"))
        if self.triage_recommendation is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "triage_recommendation", self.source_flags.get("triage_recommendation"))
        if self.edge_preserve_flag is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "edge_preserve_flag", self.source_flags.get("edge_preserve_flag"))
        if not self.effective_session_policy and isinstance(self.source_flags, dict):
            object.__setattr__(self, "effective_session_policy", self.source_flags.get("effective_session_policy") or {})
        if not self.effective_regime_policy and isinstance(self.source_flags, dict):
            object.__setattr__(self, "effective_regime_policy", self.source_flags.get("effective_regime_policy") or {})
        if not self.effective_risk_policy and isinstance(self.source_flags, dict):
            object.__setattr__(self, "effective_risk_policy", self.source_flags.get("effective_risk_policy") or {})
        if not self.effective_family_risk_profile and isinstance(self.source_flags, dict):
            object.__setattr__(
                self,
                "effective_family_risk_profile",
                self.source_flags.get("effective_family_risk_profile") or {},
            )
        if self.risk_profile_override_applied is None and isinstance(self.source_flags, dict):
            object.__setattr__(
                self,
                "risk_profile_override_applied",
                self.source_flags.get("risk_profile_override_applied"),
            )
        if not self.effective_family_survival_policy and isinstance(self.source_flags, dict):
            object.__setattr__(
                self,
                "effective_family_survival_policy",
                self.source_flags.get("effective_family_survival_policy") or {},
            )
        if self.aggressiveness_mode is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "aggressiveness_mode", self.source_flags.get("aggressiveness_mode"))
        if self.aggressiveness_adjustment is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "aggressiveness_adjustment", self.source_flags.get("aggressiveness_adjustment"))
        if self.aggressiveness_adjustment_applied is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "aggressiveness_adjustment_applied", self.source_flags.get("aggressiveness_adjustment_applied"))
        if self.primary_blocker is None and isinstance(self.source_flags, dict):
            blocker = self.source_flags.get("primary_blocker")
            if blocker is None and self.tradable_reasons_blocking:
                blocker = self.tradable_reasons_blocking[0]
            object.__setattr__(self, "primary_blocker", blocker)
        if self.truth_allows_execution is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "truth_allows_execution", self.source_flags.get("truth_allows_execution"))
        if self.class_blocks_execution is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "class_blocks_execution", self.source_flags.get("class_blocks_execution"))
        if self.debug_blocks_execution is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "debug_blocks_execution", self.source_flags.get("debug_blocks_execution"))
        if self.selection_probability is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "selection_probability", self.source_flags.get("selection_probability"))
        if self.simulation_fill_status is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "simulation_fill_status", self.source_flags.get("simulation_fill_status"))
        if self.simulation_fill_qty is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "simulation_fill_qty", self.source_flags.get("simulation_fill_qty"))
        if self.mfe is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "mfe", self.source_flags.get("mfe"))
        if self.mae is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "mae", self.source_flags.get("mae"))
        if self.simulated_pnl is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "simulated_pnl", self.source_flags.get("simulated_pnl"))
        if self.would_have_worked is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "would_have_worked", self.source_flags.get("would_have_worked"))
        if self.rejection_saved_loss is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "rejection_saved_loss", self.source_flags.get("rejection_saved_loss"))
        if self.rejection_missed_win is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "rejection_missed_win", self.source_flags.get("rejection_missed_win"))
        if self.realized_r_multiple is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "realized_r_multiple", self.source_flags.get("realized_r_multiple"))
        if self.stop_hit_before_target is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "stop_hit_before_target", self.source_flags.get("stop_hit_before_target"))
        if self.risk_plan_respected is None and isinstance(self.source_flags, dict):
            object.__setattr__(self, "risk_plan_respected", self.source_flags.get("risk_plan_respected"))
        if self.candidate_class is None:
            candidate_class = None
            if isinstance(self.source_flags, dict):
                candidate_class = self.source_flags.get("candidate_class")
            if candidate_class is None and self.candidate_status:
                status_key = str(self.candidate_status).strip().lower()
                mapping = {
                    "executable": "EXECUTABLE",
                    "near_executable": "NEAR_EXECUTABLE",
                    "advisory_only": "ADVISORY_ONLY",
                }
                candidate_class = mapping.get(status_key)
            object.__setattr__(self, "candidate_class", candidate_class)
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
