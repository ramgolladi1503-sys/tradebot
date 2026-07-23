from __future__ import annotations


def reconcile_decision_counts(counts: dict[str, int]) -> None:
    signals = int(counts.get("signals", 0))
    parts = sum(
        int(counts.get(key, 0))
        for key in (
            "direction_rejected",
            "data_blocked",
            "contracts_unresolved",
            "liquidity_rejected",
            "entry_no_fill",
            "replay_attempted",
        )
    )
    if signals != parts:
        raise ValueError("decision_count_reconciliation_failed")
    attempted = int(counts.get("replay_attempted", 0))
    evaluated_parts = sum(int(counts.get(key, 0)) for key in ("exit_no_fill", "ambiguous", "evaluated_trades"))
    if attempted != evaluated_parts:
        raise ValueError("trade_count_reconciliation_failed")


def reconcile_trade_pnl(trade: dict[str, float], *, tolerance: float = 1e-9) -> None:
    expected = (
        float(trade["gross_pnl"])
        - float(trade["spread_cost"])
        - float(trade["slippage"])
        - float(trade["brokerage"])
        - float(trade["statutory_charges"])
    )
    if abs(expected - float(trade["net_pnl"])) > tolerance:
        raise ValueError("pnl_reconciliation_failed")
