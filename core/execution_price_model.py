from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionPriceResult:
    entry_price: float | None
    exit_price: float | None
    entry_source: str | None
    exit_source: str | None
    spread_pct: float | None
    slippage_pct: float
    quote_ok: bool
    reason: str | None = None


@dataclass
class ExecutionPriceConfig:
    buy_slippage_pct: float = 0.01
    sell_slippage_pct: float = 0.01
    max_spread_pct: float = 0.25


class ExecutionPriceModel:
    def __init__(self, config: ExecutionPriceConfig | None = None):
        self.cfg = config or ExecutionPriceConfig()

    @staticmethod
    def _pos(value: Any) -> float | None:
        try:
            out = float(value)
        except Exception:
            return None
        return out if out > 0 else None

    def from_option_row(self, row: dict) -> ExecutionPriceResult:
        bid = self._pos(row.get("best_bid") or row.get("bid"))
        ask = self._pos(row.get("best_ask") or row.get("ask"))
        mark = self._pos(row.get("mark_price"))
        ltp = self._pos(row.get("ltp") or row.get("last_price"))

        spread_pct = None
        if bid is not None and ask is not None:
            ref = mark or ltp or ((bid + ask) / 2.0)
            if ref and ref > 0:
                spread_pct = (ask - bid) / ref

        if bid is None and ask is None and mark is None and ltp is None:
            return ExecutionPriceResult(
                entry_price=None,
                exit_price=None,
                entry_source=None,
                exit_source=None,
                spread_pct=None,
                slippage_pct=0.0,
                quote_ok=False,
                reason="missing_quote",
            )

        if spread_pct is not None and spread_pct > float(self.cfg.max_spread_pct):
            return ExecutionPriceResult(
                entry_price=None,
                exit_price=None,
                entry_source=None,
                exit_source=None,
                spread_pct=spread_pct,
                slippage_pct=0.0,
                quote_ok=False,
                reason="spread_too_wide",
            )

        buy_base = ask or mark or ltp or bid
        sell_base = bid or mark or ltp or ask
        if buy_base is None or sell_base is None:
            return ExecutionPriceResult(
                entry_price=None,
                exit_price=None,
                entry_source=None,
                exit_source=None,
                spread_pct=spread_pct,
                slippage_pct=0.0,
                quote_ok=False,
                reason="incomplete_quote",
            )

        entry_price = buy_base * (1.0 + float(self.cfg.buy_slippage_pct))
        exit_price = sell_base * (1.0 - float(self.cfg.sell_slippage_pct))
        entry_source = "ask" if ask is not None else ("mark" if mark is not None else ("ltp" if ltp is not None else "bid"))
        exit_source = "bid" if bid is not None else ("mark" if mark is not None else ("ltp" if ltp is not None else "ask"))

        return ExecutionPriceResult(
            entry_price=round(float(entry_price), 4),
            exit_price=round(float(exit_price), 4),
            entry_source=entry_source,
            exit_source=exit_source,
            spread_pct=spread_pct,
            slippage_pct=max(float(self.cfg.buy_slippage_pct), float(self.cfg.sell_slippage_pct)),
            quote_ok=True,
            reason=None,
        )
