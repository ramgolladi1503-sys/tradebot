from __future__ import annotations

from dataclasses import dataclass

from .signal_contract import OptionRight


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

    def validate_at(self, decision_ts: str) -> None:
        if not self.trading_symbol or not self.instrument_token:
            raise ValueError("missing_contract_identity")
        if self.underlying != "NIFTY":
            raise ValueError("unsupported_underlying")
        if self.strike <= 0 or self.tick_size <= 0 or self.lot_size <= 0:
            raise ValueError("invalid_contract_terms")
        if not self.point_in_time_source:
            raise ValueError("missing_point_in_time_source")
        if self.listed_from > decision_ts or self.listed_until <= decision_ts:
            raise ValueError("contract_not_listed_at_decision_ts")


def reject_current_master_as_historical_authority(source_kind: str) -> None:
    if source_kind == "current_instrument_master":
        raise ValueError("current_instrument_master_cannot_certify_expired_contract")
