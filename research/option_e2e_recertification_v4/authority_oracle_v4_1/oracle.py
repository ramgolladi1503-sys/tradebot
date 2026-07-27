from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


CURRENT_MASTER_KINDS = frozenset({"current_master", "current_instrument_master"})


@dataclass(frozen=True)
class ContractIdentity:
    instrument_token: str
    trading_symbol: str
    underlying: str
    expiry: str
    strike: float
    option_right: str

    def normalized(self) -> tuple[str, str, str, str, float, str]:
        return (
            self.instrument_token.strip(),
            self.trading_symbol.strip(),
            self.underlying.strip().upper(),
            self.expiry.strip(),
            float(self.strike),
            self.option_right.strip().upper(),
        )

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not self.instrument_token.strip() or not self.trading_symbol.strip():
            issues.append("missing_token_or_symbol")
        if not self.expiry.strip():
            issues.append("missing_expiry")
        if self.strike <= 0:
            issues.append("invalid_strike")
        if self.option_right.strip().upper() not in {"CE", "PE"}:
            issues.append("invalid_option_right")
        return tuple(issues)


@dataclass(frozen=True)
class ContractMasterEvidence:
    identity: ContractIdentity
    source_kind: str
    created_at: str
    complete_universe: bool


@dataclass(frozen=True)
class QuoteFileEvidence:
    path: str
    inferred_identity: ContractIdentity | None


@dataclass(frozen=True)
class QuoteRowEvidence:
    identity: ContractIdentity
    quote_ts: str
    row_expiry: str | None
    row_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceManifestEvidence:
    created_at: str
    dataset_hash: str
    row_count: int


@dataclass(frozen=True)
class ObservedUniverseEvidence:
    expected_identities: tuple[ContractIdentity, ...]
    observed_identities: tuple[ContractIdentity, ...]


@dataclass(frozen=True)
class LotSizeEvidence:
    observed_lot_size: int
    independent_lot_size: int
    source: str


@dataclass(frozen=True)
class AuthorityOracleInput:
    decision_ts: str
    target_identity: ContractIdentity
    master: ContractMasterEvidence | None = None
    quote_file: QuoteFileEvidence | None = None
    quote_rows: tuple[QuoteRowEvidence, ...] = ()
    manifest: SourceManifestEvidence | None = None
    observed_universe: ObservedUniverseEvidence | None = None
    lot_size: LotSizeEvidence | None = None


@dataclass(frozen=True)
class AuthorityOracleVerdict:
    status: str
    reason_codes: tuple[str, ...]
    proves_observed_existence: bool
    proves_universe_completeness: bool
    allowed_for_live_execution: bool = False
    broker_api_called: False = False
    is_order_action: False = False


def verify_contract_authority(evidence: AuthorityOracleInput) -> AuthorityOracleVerdict:
    issues: list[str] = []
    target = evidence.target_identity
    issues.extend(f"target_{issue}" for issue in target.validate())
    decision_dt = _parse_datetime(evidence.decision_ts, "invalid_decision_ts", issues)
    expiry_day = _parse_date(target.expiry, "target_invalid_expiry", issues)

    if evidence.master is None:
        issues.append("master_absent")
    else:
        _check_master(evidence.master, target, evidence.decision_ts, issues)

    if evidence.quote_file is None:
        issues.append("quote_file_absent")
    else:
        _check_quote_file(evidence.quote_file, target, issues)

    observed_from_rows = False
    if not evidence.quote_rows:
        issues.append("quote_rows_absent")
    for row in evidence.quote_rows:
        observed_from_rows = _check_quote_row(row, target, decision_dt, expiry_day, issues) or observed_from_rows

    if evidence.manifest is None:
        issues.append("manifest_absent")
    else:
        _check_manifest(evidence.manifest, evidence.decision_ts, issues)

    universe_complete = False
    if evidence.observed_universe is None:
        issues.append("observed_universe_absent")
    else:
        universe_complete = _check_observed_universe(evidence.observed_universe, issues)

    if evidence.lot_size is None:
        issues.append("lot_size_authority_absent")
    else:
        _check_lot_size(evidence.lot_size, issues)

    seen_identities = _all_identity_sources(evidence)
    if _has_conflicting_duplicates(seen_identities):
        issues.append("duplicate_conflicting_identities")

    reason_codes = tuple(dict.fromkeys(issues))
    return AuthorityOracleVerdict(
        status="PASS" if not reason_codes else "FAIL",
        reason_codes=reason_codes,
        proves_observed_existence=observed_from_rows and not _has_identity_issue(reason_codes),
        proves_universe_completeness=universe_complete and "master_not_complete_universe" not in reason_codes,
    )


def _check_master(
    master: ContractMasterEvidence,
    target: ContractIdentity,
    decision_ts: str,
    issues: list[str],
) -> None:
    source_kind = master.source_kind.strip().lower()
    if source_kind in CURRENT_MASTER_KINDS:
        issues.append("current_master_alone_not_authority")
    if master.identity.normalized() != target.normalized():
        issues.append("master_target_identity_mismatch")
    if master.created_at > decision_ts:
        issues.append("master_created_after_decision")
    if not master.complete_universe:
        issues.append("master_not_complete_universe")


def _check_quote_file(file_evidence: QuoteFileEvidence, target: ContractIdentity, issues: list[str]) -> None:
    if not file_evidence.path.strip():
        issues.append("quote_filename_missing")
    if file_evidence.inferred_identity is None:
        issues.append("quote_filename_alone_not_authority")
        return
    if file_evidence.inferred_identity.normalized() != target.normalized():
        issues.append("quote_filename_identity_mismatch")


def _check_quote_row(
    row: QuoteRowEvidence,
    target: ContractIdentity,
    decision_dt: datetime | None,
    expiry_day: date | None,
    issues: list[str],
) -> bool:
    if row.identity.normalized() != target.normalized():
        issues.append("quote_row_identity_mismatch")
        return False
    if row.row_expiry is None or not row.row_expiry.strip():
        issues.append("quote_row_without_expiry_not_authority")
    elif row.row_expiry.strip() != target.expiry:
        issues.append("quote_row_expiry_mismatch")
    for field_name in ("instrument_token", "trading_symbol", "expiry"):
        value = row.row_metadata.get(field_name)
        expected = getattr(target, field_name)
        if value is not None and str(value).strip() != str(expected):
            issues.append("quote_row_metadata_mismatch")
    quote_dt = _parse_datetime(row.quote_ts, "invalid_quote_ts", issues)
    if quote_dt is not None and decision_dt is not None and quote_dt > decision_dt:
        issues.append("quote_after_decision")
    if quote_dt is not None and expiry_day is not None and quote_dt.date() > expiry_day:
        issues.append("post_expiry_quote")
    return row.row_expiry == target.expiry


def _check_manifest(manifest: SourceManifestEvidence, decision_ts: str, issues: list[str]) -> None:
    if not manifest.dataset_hash.strip():
        issues.append("manifest_missing_dataset_hash")
    if manifest.row_count <= 0:
        issues.append("manifest_empty_dataset")
    if manifest.created_at > decision_ts:
        issues.append("future_created_manifest")


def _check_observed_universe(universe: ObservedUniverseEvidence, issues: list[str]) -> bool:
    expected = {identity.normalized() for identity in universe.expected_identities}
    observed = {identity.normalized() for identity in universe.observed_identities}
    if expected - observed:
        issues.append("observed_universe_incomplete")
        return False
    if not expected:
        issues.append("expected_universe_empty")
        return False
    return True


def _check_lot_size(lot_size: LotSizeEvidence, issues: list[str]) -> None:
    if lot_size.observed_lot_size <= 0 or lot_size.independent_lot_size <= 0:
        issues.append("invalid_lot_size")
    if not lot_size.source.strip():
        issues.append("lot_size_source_missing")
    if lot_size.observed_lot_size != lot_size.independent_lot_size:
        issues.append("lot_size_independent_mismatch")


def _all_identity_sources(evidence: AuthorityOracleInput) -> list[ContractIdentity]:
    identities = [evidence.target_identity]
    if evidence.master is not None:
        identities.append(evidence.master.identity)
    if evidence.quote_file is not None and evidence.quote_file.inferred_identity is not None:
        identities.append(evidence.quote_file.inferred_identity)
    identities.extend(row.identity for row in evidence.quote_rows)
    return identities


def _has_conflicting_duplicates(identities: list[ContractIdentity]) -> bool:
    by_token: dict[str, tuple[str, str, str, float, str]] = {}
    by_symbol: dict[str, tuple[str, str, str, float, str]] = {}
    for identity in identities:
        token, symbol, underlying, expiry, strike, right = identity.normalized()
        token_payload = (symbol, underlying, expiry, strike, right)
        symbol_payload = (token, underlying, expiry, strike, right)
        if token in by_token and by_token[token] != token_payload:
            return True
        if symbol in by_symbol and by_symbol[symbol] != symbol_payload:
            return True
        by_token[token] = token_payload
        by_symbol[symbol] = symbol_payload
    return False


def _has_identity_issue(reason_codes: tuple[str, ...]) -> bool:
    return any("identity_mismatch" in code or "missing_token_or_symbol" in code for code in reason_codes)


def _parse_datetime(value: str, reason_code: str, issues: list[str]) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        issues.append(reason_code)
        return None


def _parse_date(value: str, reason_code: str, issues: list[str]) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        issues.append(reason_code)
        return None
