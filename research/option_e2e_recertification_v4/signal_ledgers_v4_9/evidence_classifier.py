from __future__ import annotations


def classify_evidence(record: dict[str, object]) -> str:
    kind = str(record.get("strategy_kind") or "")
    if kind == "candidate_generator_strategy":
        return "DIRECTIONAL_LONG_OPTION_ELIGIBLE"
    if record.get("strategy_id") == "NO_TRADE_CHOP":
        return "NO_TRADE_FILTER"
    if record.get("strategy_id") == "PAIRS_ARBITRAGE":
        return "MULTI_ASSET_OR_PAIR"
    if kind in {"helper_module", "aggregate_engine"}:
        return "HELPER_OR_AGGREGATE"
    if not record.get("module_exists_at_foundation", False):
        return "IMPLEMENTATION_MISSING"
    return "OUT_OF_SCOPE"
