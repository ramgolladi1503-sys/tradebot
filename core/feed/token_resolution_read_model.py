"""Pure token resolution read-model helpers for feed subscriptions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

_DEFAULT_OPTION_RANK: tuple[float, int, float, int, int] = (float("inf"), 1, float("inf"), 2, 0)


@dataclass(frozen=True)
class OptionInstrumentMeta:
    strike: float | None = None
    instrument_type: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "OptionInstrumentMeta":
        raw = dict(value or {})
        strike_raw = raw.get("strike")
        try:
            strike = float(strike_raw) if strike_raw is not None else None
        except Exception:
            strike = None
        return cls(strike=strike, instrument_type=str(raw.get("instrument_type") or "").upper())

    def to_payload(self) -> dict[str, Any]:
        return {"strike": self.strike, "instrument_type": self.instrument_type}


@dataclass(frozen=True)
class SymbolResolutionInput:
    symbol: str
    exchange: str
    expiry: Any
    ltp: float | None
    ltp_source: str
    atm: int | None
    strikes_around: int
    step: float | None
    index_token: Any = None
    index_token_source: str = "missing"
    option_tokens_raw: Iterable[Any] | None = None
    option_meta_by_token: Mapping[int, Mapping[str, Any]] = field(default_factory=dict)
    min_option_tokens: int = 1


@dataclass(frozen=True)
class SymbolResolutionReadModel:
    row: dict[str, Any]
    tokens: tuple[int, ...]
    underlying_tokens: tuple[int, ...]
    underlying_token_to_symbol: dict[int, str]
    token_to_symbol: dict[int, str]
    option_rank_by_token: dict[int, tuple[float, int, float, int, int]]
    token_exchange_hint: dict[int, str]


@dataclass(frozen=True)
class TokenResolutionReadModel:
    tokens: tuple[int, ...]
    resolution_rows: tuple[dict[str, Any], ...]
    underlying_tokens: frozenset[int]
    underlying_token_to_symbol: dict[int, str]
    token_to_symbol: dict[int, str]
    option_rank_by_token: dict[int, tuple[float, int, float, int, int]]
    token_exchange_hint: dict[int, str]
    option_counts_by_symbol: dict[str, int]
    option_min_required_by_symbol: dict[str, int]

    def to_payload(self) -> dict[str, Any]:
        return {
            "tokens": list(self.tokens),
            "resolution": [dict(row) for row in self.resolution_rows],
            "underlying_tokens": sorted(int(token) for token in self.underlying_tokens),
            "underlying_token_to_symbol": dict(self.underlying_token_to_symbol),
            "token_to_symbol": dict(self.token_to_symbol),
            "option_counts_by_symbol": dict(self.option_counts_by_symbol),
            "option_min_required_by_symbol": dict(self.option_min_required_by_symbol),
        }


def normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def normalize_exchange(exchange: Any, *, symbol: Any = None) -> str:
    text = str(exchange or "").strip().upper()
    if text:
        return text
    return "BFO" if normalize_symbol(symbol) == "SENSEX" else "NFO"


def normalize_positive_tokens(values: Iterable[Any] | None) -> tuple[int, ...]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in list(values or []):
        try:
            token = int(raw)
        except Exception:
            continue
        if token <= 0 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return tuple(out)


def expiry_key(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        text = str(value).strip()
        if not text:
            return None
        text = text.split("T", 1)[0]
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return None


def infer_atm_strike(ltp: float | None, step: float | None) -> int | None:
    if ltp is None or step is None:
        return None
    try:
        step_val = float(step)
        if step_val <= 0:
            return None
        return int(round(float(ltp) / step_val) * step_val)
    except Exception:
        return None


def option_distance_rank(
    meta: Mapping[str, Any] | OptionInstrumentMeta | None,
    *,
    atm: int | None,
    step: float | None,
    token: Any,
) -> tuple[float, int, float, int, int]:
    try:
        token_int = int(token)
    except Exception:
        token_int = 0
    if atm is None or step is None:
        return (_DEFAULT_OPTION_RANK[0], _DEFAULT_OPTION_RANK[1], _DEFAULT_OPTION_RANK[2], _DEFAULT_OPTION_RANK[3], token_int)
    meta_obj = meta if isinstance(meta, OptionInstrumentMeta) else OptionInstrumentMeta.from_mapping(meta)
    if meta_obj.strike is None:
        return (_DEFAULT_OPTION_RANK[0], _DEFAULT_OPTION_RANK[1], _DEFAULT_OPTION_RANK[2], _DEFAULT_OPTION_RANK[3], token_int)
    try:
        step_val = float(step)
        if step_val <= 0:
            return (_DEFAULT_OPTION_RANK[0], _DEFAULT_OPTION_RANK[1], _DEFAULT_OPTION_RANK[2], _DEFAULT_OPTION_RANK[3], token_int)
        strike_val = float(meta_obj.strike)
        dist_abs = abs(strike_val - float(atm))
        dist_steps = dist_abs / step_val
    except Exception:
        return (_DEFAULT_OPTION_RANK[0], _DEFAULT_OPTION_RANK[1], _DEFAULT_OPTION_RANK[2], _DEFAULT_OPTION_RANK[3], token_int)
    opt_type = str(meta_obj.instrument_type or "").upper()
    is_otm = (opt_type == "CE" and strike_val > float(atm)) or (opt_type == "PE" and strike_val < float(atm))
    otm_rank = 1 if is_otm else 0
    type_rank = 0 if opt_type == "CE" else (1 if opt_type == "PE" else 2)
    return (dist_steps, otm_rank, dist_abs, type_rank, token_int)


def normalize_and_rank_option_tokens(
    option_tokens_raw: Iterable[Any] | None,
    *,
    option_meta_by_token: Mapping[int, Mapping[str, Any]] | None,
    atm: int | None,
    step: float | None,
) -> tuple[tuple[int, ...], dict[int, tuple[float, int, float, int, int]]]:
    meta_by_token = dict(option_meta_by_token or {})
    option_tokens = list(normalize_positive_tokens(option_tokens_raw))
    option_tokens.sort(
        key=lambda token: option_distance_rank(meta_by_token.get(int(token)), atm=atm, step=step, token=int(token))
    )
    ranks = {
        int(token): option_distance_rank(meta_by_token.get(int(token)), atm=atm, step=step, token=int(token))
        for token in option_tokens
    }
    return tuple(option_tokens), ranks


def option_fail_reason(*, expiry: Any, atm: int | None, option_count: int, min_required: int) -> str | None:
    if expiry is None:
        return "expiry_unavailable"
    if atm is None:
        return "atm_unavailable"
    if int(option_count or 0) < max(1, int(min_required or 1)):
        return "option_tokens_under_min"
    return None


def selected_option_strikes(
    tokens: Iterable[Any] | None,
    *,
    option_meta_by_token: Mapping[int, Mapping[str, Any]] | None,
) -> tuple[tuple[float, ...], int, int]:
    selected: dict[float, set[str]] = {}
    meta_by_token = dict(option_meta_by_token or {})
    for token in normalize_positive_tokens(tokens):
        meta = OptionInstrumentMeta.from_mapping(meta_by_token.get(int(token)))
        if meta.strike is not None and meta.instrument_type in {"CE", "PE"}:
            selected.setdefault(float(meta.strike), set()).add(meta.instrument_type)
    two_sided = sum(1 for legs in selected.values() if {"CE", "PE"}.issubset(legs))
    return tuple(sorted(selected.keys())), len(selected), int(two_sided)


def build_symbol_resolution_read_model(inputs: SymbolResolutionInput) -> SymbolResolutionReadModel:
    symbol = normalize_symbol(inputs.symbol)
    exchange = normalize_exchange(inputs.exchange, symbol=symbol)
    expiry_norm = expiry_key(inputs.expiry)
    step = float(inputs.step) if inputs.step is not None else None
    min_required = max(1, int(inputs.min_option_tokens or 1))
    option_tokens, ranks = normalize_and_rank_option_tokens(
        inputs.option_tokens_raw,
        option_meta_by_token=inputs.option_meta_by_token,
        atm=inputs.atm,
        step=step,
    )
    fail_reason = option_fail_reason(
        expiry=inputs.expiry,
        atm=inputs.atm,
        option_count=len(option_tokens),
        min_required=min_required,
    )
    final_option_tokens = () if fail_reason == "option_tokens_under_min" else option_tokens
    tokens: list[int] = []
    underlying_tokens: list[int] = []
    underlying_token_to_symbol: dict[int, str] = {}
    token_to_symbol: dict[int, str] = {}
    token_exchange_hint: dict[int, str] = {}
    try:
        index_token = int(inputs.index_token) if inputs.index_token is not None else None
    except Exception:
        index_token = None
    if index_token is not None and index_token > 0:
        tokens.append(index_token)
        underlying_tokens.append(index_token)
        underlying_token_to_symbol[index_token] = symbol
        token_to_symbol[index_token] = symbol
        token_exchange_hint[index_token] = "BSE" if symbol == "SENSEX" else "NSE"
    for token in final_option_tokens:
        if token not in tokens:
            tokens.append(int(token))
        token_to_symbol[int(token)] = symbol
        token_exchange_hint[int(token)] = exchange
    strikes, strike_count, two_sided_count = selected_option_strikes(
        final_option_tokens,
        option_meta_by_token=inputs.option_meta_by_token,
    )
    row = {
        "symbol": symbol,
        "exchange": exchange,
        "expiry": expiry_norm,
        "ltp": inputs.ltp,
        "ltp_source": str(inputs.ltp_source or "missing"),
        "atm": inputs.atm,
        "strikes_around": int(inputs.strikes_around),
        "step": step,
        "tokens": list(tokens),
        "count": len(tokens),
        "resolved_count": len(tokens),
        "option_count": len(final_option_tokens),
        "resolved_option_count": len(option_tokens),
        "option_min_required": min_required,
        "option_fail_reason": fail_reason,
        "option_strikes_selected": list(strikes),
        "option_strike_count": int(strike_count),
        "option_two_sided_strike_count": int(two_sided_count),
        "index_token": index_token,
        "index_token_source": str(inputs.index_token_source if index_token else "missing"),
    }
    return SymbolResolutionReadModel(
        row=row,
        tokens=tuple(tokens),
        underlying_tokens=tuple(underlying_tokens),
        underlying_token_to_symbol=underlying_token_to_symbol,
        token_to_symbol=token_to_symbol,
        option_rank_by_token=ranks,
        token_exchange_hint=token_exchange_hint,
    )


def combine_symbol_resolution_models(models: Iterable[SymbolResolutionReadModel] | None) -> TokenResolutionReadModel:
    tokens: list[int] = []
    rows: list[dict[str, Any]] = []
    underlying_tokens: set[int] = set()
    underlying_token_to_symbol: dict[int, str] = {}
    token_to_symbol: dict[int, str] = {}
    option_rank_by_token: dict[int, tuple[float, int, float, int, int]] = {}
    token_exchange_hint: dict[int, str] = {}
    for model in list(models or []):
        tokens.extend(int(token) for token in model.tokens if int(token) > 0)
        rows.append(dict(model.row))
        underlying_tokens.update(int(token) for token in model.underlying_tokens if int(token) > 0)
        underlying_token_to_symbol.update(model.underlying_token_to_symbol)
        token_to_symbol.update(model.token_to_symbol)
        option_rank_by_token.update(model.option_rank_by_token)
        token_exchange_hint.update(model.token_exchange_hint)
    deduped_tokens = tuple(dict.fromkeys(tokens))
    return TokenResolutionReadModel(
        tokens=deduped_tokens,
        resolution_rows=tuple(rows),
        underlying_tokens=frozenset(underlying_tokens),
        underlying_token_to_symbol=underlying_token_to_symbol,
        token_to_symbol=token_to_symbol,
        option_rank_by_token=option_rank_by_token,
        token_exchange_hint=token_exchange_hint,
        option_counts_by_symbol={
            normalize_symbol(row.get("symbol")): int(row.get("option_count") or 0)
            for row in rows
            if normalize_symbol(row.get("symbol"))
        },
        option_min_required_by_symbol={
            normalize_symbol(row.get("symbol")): int(row.get("option_min_required") or 0)
            for row in rows
            if normalize_symbol(row.get("symbol"))
        },
    )


__all__ = [
    "OptionInstrumentMeta",
    "SymbolResolutionInput",
    "SymbolResolutionReadModel",
    "TokenResolutionReadModel",
    "build_symbol_resolution_read_model",
    "combine_symbol_resolution_models",
    "expiry_key",
    "infer_atm_strike",
    "normalize_and_rank_option_tokens",
    "normalize_exchange",
    "normalize_positive_tokens",
    "normalize_symbol",
    "option_distance_rank",
    "option_fail_reason",
    "selected_option_strikes",
]
