from __future__ import annotations

from dataclasses import dataclass

from .signal_contract import OptionRight
from .time_utils import expiry_cutoff_ts, parse_ts


@dataclass(frozen=True)
class OptionContractMetadata:
    trading_symbol: str
    instrument_token: str
    underlying: str
    option_right: OptionRight
    strike: float
    expiry: str
    tick_size: float
    lot_size: int
    listed_from: str
    listed_until: str
    provider: str
    dataset_hash: str
    metadata_hash: str
    point_in_time_source: str

    def validate_at(self, decision_ts: str, *, expiry_cutoff: str = "15:30:00") -> None:
        if not self.trading_symbol or not self.instrument_token:
            raise ValueError("missing_contract_identity")
        if self.underlying != "NIFTY":
            raise ValueError("unsupported_underlying")
        if self.strike <= 0 or self.tick_size <= 0 or self.lot_size <= 0:
            raise ValueError("invalid_contract_terms")
        if not self.dataset_hash or not self.metadata_hash:
            raise ValueError("missing_contract_hash")
        if not self.point_in_time_source:
            raise ValueError("missing_point_in_time_source")
        decision = parse_ts(decision_ts)
        listed_from = parse_ts(self.listed_from)
        listed_until = parse_ts(self.listed_until)
        cutoff = expiry_cutoff_ts(self.expiry, cutoff=expiry_cutoff)
        if listed_until.date() != cutoff.date() or listed_until > cutoff:
            raise ValueError("expiry_metadata_mismatch")
        if decision < listed_from or decision >= listed_until or decision >= cutoff:
            raise ValueError("contract_not_listed_at_decision_ts")


def reject_current_master_as_historical_authority(source_kind: str) -> None:
    normalized = " ".join(str(source_kind).strip().lower().replace("-", "_").split())
    if normalized in {"current_instrument_master", "current instrument master"}:
        raise ValueError("current_instrument_master_cannot_certify_expired_contract")
