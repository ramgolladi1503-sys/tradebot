from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .signal_contract import OptionRight
from .time_utils import expiry_cutoff_ts, parse_ts


class AuthorityTier(str, Enum):
    HISTORICAL_INSTRUMENT_SNAPSHOT = "A_HISTORICAL_INSTRUMENT_SNAPSHOT"
    CONTEMPORANEOUS_QUOTE = "B_CONTEMPORANEOUS_SELF_DESCRIBING_QUOTE"
    COMPOSITE_IDENTITY = "C_COMPOSITE_IDENTITY"
    CURRENT_MASTER_SUPPLEMENT = "D_CURRENT_MASTER_SUPPLEMENT"


@dataclass(frozen=True)
class QuoteContractEvidence:
    observed_ts: str
    trading_symbol: str
    instrument_token: str
    underlying: str
    option_right: OptionRight
    strike: float
    expiry: str
    provider: str
    source_hash: str
    bid: float
    ask: float
    file_created_ts: str | None = None
    filename_symbol: str | None = None
    manifest_hash: str | None = None

    def validate_observed_existence(self, *, decision_ts: str) -> None:
        if not self.trading_symbol or not self.instrument_token:
            raise ValueError("missing_quote_contract_identity")
        if self.underlying != "NIFTY":
            raise ValueError("unsupported_underlying")
        if self.strike <= 0:
            raise ValueError("invalid_quote_strike")
        if not self.expiry:
            raise ValueError("missing_quote_expiry")
        if not self.provider or not self.source_hash:
            raise ValueError("missing_quote_source_identity")
        if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid:
            raise ValueError("invalid_quote_values")
        observed = parse_ts(self.observed_ts)
        decision = parse_ts(decision_ts)
        if observed > decision:
            raise ValueError("quote_after_decision")
        if observed >= expiry_cutoff_ts(self.expiry):
            raise ValueError("post_expiry_quote")
        if self.file_created_ts is not None and parse_ts(self.file_created_ts) > decision:
            raise ValueError("future_created_manifest")
        if self.filename_symbol and self.filename_symbol != self.trading_symbol:
            raise ValueError("filename_row_symbol_mismatch")


@dataclass(frozen=True)
class CompositeAuthorityVerdict:
    observed_existence: bool
    universe_completeness: str
    lot_size_authority: str
    tick_size_authority: str
    authority_tiers: tuple[AuthorityTier, ...]
    blockers: tuple[str, ...]

    @property
    def full_contract_authority(self) -> bool:
        return (
            self.observed_existence
            and self.universe_completeness == "OBSERVED_DATASET_UNIVERSE"
            and self.lot_size_authority == "PASS"
            and self.tick_size_authority == "PASS"
            and not self.blockers
        )


def certify_quote_observed_existence(evidence: QuoteContractEvidence, *, decision_ts: str) -> CompositeAuthorityVerdict:
    evidence.validate_observed_existence(decision_ts=decision_ts)
    blockers = []
    if not evidence.manifest_hash:
        blockers.append("MANIFEST_IDENTITY_MISSING")
    return CompositeAuthorityVerdict(
        observed_existence=True,
        universe_completeness="OBSERVED_CONTRACT_ONLY",
        lot_size_authority="LOT_SIZE_AUTHORITY_MISSING",
        tick_size_authority="TICK_SIZE_AUTHORITY_MISSING",
        authority_tiers=(AuthorityTier.CONTEMPORANEOUS_QUOTE,),
        blockers=tuple(blockers),
    )
