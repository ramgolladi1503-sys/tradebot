"""Source-backed candidate feed dependency declarations.

This registry is descriptive and fail-closed. A declaration does not grant
execution authority; entries with partial identity or historical/advisory
scope remain blocked by the symbol safety consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path
from typing import Iterable, Mapping


VERIFIED_DECLARATION = "VERIFIED_DECLARATION"
PARTIAL_DECLARATION = "PARTIAL_DECLARATION"
UNKNOWN_BLOCKED = "UNKNOWN_BLOCKED"

_VALID_AUTHORITY_STATUSES = {
    VERIFIED_DECLARATION,
    PARTIAL_DECLARATION,
    UNKNOWN_BLOCKED,
}
_VALID_DOMAINS = {
    "INDEX_SPOT",
    "INDEX_FUTURES",
    "INDEX_OPTIONS",
    "STOCK_SPOT",
    "STOCK_OPTIONS",
}


@dataclass(frozen=True)
class CandidateFeedDependencySpec:
    candidate_id: str
    authority_status: str
    required_domains: tuple[str, ...]
    # (domain, canonical identity or None when the source requires a dynamic
    # identity but the authoritative runtime mapping is unavailable).
    required_identities: tuple[tuple[str, str | None], ...]
    source_sha256: tuple[tuple[str, str], ...]
    execution_scope: str
    unresolved_requirements: tuple[str, ...] = ()
    # None means the source contract did not establish this category. An
    # empty tuple is reserved for an authoritative declaration of no inputs.
    optional_domains: tuple[str, ...] | None = None
    fallback_inputs: tuple[str, ...] | None = None
    breadth_inputs: tuple[str, ...] | None = None
    freshness_policy: tuple[str, ...] | None = None

    @property
    def execution_eligible(self) -> bool:
        return (
            self.authority_status == VERIFIED_DECLARATION
            and self.execution_scope == "EXECUTION"
            and all(identity is not None for _, identity in self.required_identities)
            and not self.unresolved_requirements
        )


@dataclass(frozen=True)
class CandidateDependencyResolution:
    status: str
    reason: str
    candidate_id: str | None
    required_domains: tuple[str, ...] = ()
    required_identities: tuple[tuple[str, str | None], ...] = ()
    source_sha256: tuple[tuple[str, str], ...] = ()
    execution_eligible: bool = False
    optional_domains: tuple[str, ...] | None = None
    fallback_inputs: tuple[str, ...] | None = None
    breadth_inputs: tuple[str, ...] | None = None
    freshness_policy: tuple[str, ...] | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "candidate_id": self.candidate_id,
            "required_domains": list(self.required_domains),
            "required_identities": [
                {"domain": domain, "identity": identity}
                for domain, identity in self.required_identities
            ],
            "source_sha256": [
                {"path": path, "sha256": digest}
                for path, digest in self.source_sha256
            ],
            "optional_domains": list(self.optional_domains) if self.optional_domains is not None else None,
            "fallback_inputs": list(self.fallback_inputs) if self.fallback_inputs is not None else None,
            "breadth_inputs": list(self.breadth_inputs) if self.breadth_inputs is not None else None,
            "freshness_policy": list(self.freshness_policy) if self.freshness_policy is not None else None,
            "execution_eligible": self.execution_eligible,
            "registry_coverage": self.candidate_id is not None and self.status != UNKNOWN_BLOCKED,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "append": False,
        }


REGISTRY_ENTRIES: tuple[CandidateFeedDependencySpec, ...] = (
    CandidateFeedDependencySpec(
        candidate_id="CAS_MORNING_REVERSAL_SHORT_HORIZON_V1",
        authority_status=VERIFIED_DECLARATION,
        required_domains=("INDEX_SPOT",),
        required_identities=(("INDEX_SPOT", "NIFTY"),),
        source_sha256=(
            ("core/read_only_strategy_registry.py", "1810fb68441617c2614296b8dcffe96eee947878c692ceae653654196e51ebee"),
            ("core/cas_morning_reversal_advisory.py", "08136c2e8f21fceef20b87ae72c0a72573987d861cef7f795aba60701fc962d2"),
        ),
        execution_scope="ADVISORY_ONLY",
        unresolved_requirements=("advisory_contract_has_no_execution_authority",),
    ),
    CandidateFeedDependencySpec(
        candidate_id="INTRADAY_OPENING_DRIVE_V1",
        authority_status=PARTIAL_DECLARATION,
        required_domains=("INDEX_SPOT", "INDEX_FUTURES", "INDEX_OPTIONS"),
        required_identities=(
            ("INDEX_SPOT", "NIFTY 50"),
            ("INDEX_FUTURES", None),
            ("INDEX_OPTIONS", None),
        ),
        source_sha256=(
            ("docs/research/candidates/INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.json", "10087e1166d8e11cde194960707e3b490d0ca30ec1df9f30bc3c42889c77cc0b"),
            ("core/paper_shadow/strategy_shadow_adapter.py", "4b6ed99ee10c891949ac1f1cae8018320990e19644fc11994ec2372afea73ef9"),
        ),
        execution_scope="HISTORICAL_SHADOW_ONLY",
        unresolved_requirements=(
            "authoritative_nifty_futures_contract_identity_unavailable",
            "dynamic_atm_option_identity_not_bound_to_health_evidence",
            "candidate_spec_terminally_frozen_historical_research_halted",
        ),
    ),
    CandidateFeedDependencySpec(
        candidate_id="S1_MOMENTUM_OVERNIGHT_V1",
        authority_status=PARTIAL_DECLARATION,
        required_domains=("INDEX_SPOT",),
        required_identities=(("INDEX_SPOT", "NIFTY50"),),
        source_sha256=(
            ("docs/research/candidates/S1_MOMENTUM_OVERNIGHT_V1/FROZEN_SPEC.json", "3e60d58c9caaa28d72fb1a79553c477cab4cd27f4d2ed27c66c4a392da1a4b7a"),
            ("core/paper_shadow/strategy_shadow_adapter.py", "4b6ed99ee10c891949ac1f1cae8018320990e19644fc11994ec2372afea73ef9"),
            ("core/candidate_audits/nifty_overnight_drift.py", "1fdf2f9ccda8c019568fcc20ae2928fa0ccfb740d4801d1d59a001162d0889f0"),
        ),
        execution_scope="HISTORICAL_CANDIDATE_ONLY",
        unresolved_requirements=(
            "identity_scoped_spot_freshness_not_produced",
            "t1_heritage_is_separate_required_authority",
            "frozen_candidate_not_paper_or_live_authorized",
        ),
    ),
    CandidateFeedDependencySpec(
        candidate_id="S4_MONDAY_OVERNIGHT_V1",
        authority_status=PARTIAL_DECLARATION,
        required_domains=("INDEX_SPOT",),
        required_identities=(("INDEX_SPOT", "NIFTY50"),),
        source_sha256=(
            ("docs/research/candidates/S4_MONDAY_OVERNIGHT_V1/FROZEN_SPEC.json", "eed4ceed76a593bb253fa795558d1a185ae0f0c698b2686d31b4be680c889d32"),
            ("core/paper_shadow/strategy_shadow_adapter.py", "4b6ed99ee10c891949ac1f1cae8018320990e19644fc11994ec2372afea73ef9"),
            ("core/candidate_audits/nifty_overnight_drift.py", "1fdf2f9ccda8c019568fcc20ae2928fa0ccfb740d4801d1d59a001162d0889f0"),
        ),
        execution_scope="HISTORICAL_CANDIDATE_ONLY",
        unresolved_requirements=(
            "identity_scoped_spot_freshness_not_produced",
            "t1_heritage_is_separate_required_authority",
            "frozen_candidate_not_paper_or_live_authorized",
        ),
    ),
    CandidateFeedDependencySpec(
        candidate_id="DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION",
        authority_status=PARTIAL_DECLARATION,
        required_domains=("INDEX_FUTURES", "INDEX_SPOT", "INDEX_OPTIONS"),
        required_identities=(
            ("INDEX_FUTURES", None),
            ("INDEX_SPOT", "NIFTY 50"),
            ("INDEX_OPTIONS", None),
        ),
        source_sha256=(
            ("docs/research/candidates/DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION/FROZEN_SPEC.json", "da1beaef784ec61a6d4899448915c4c73f5ffe736c349aaed1793dd3cb5cab03"),
            ("core/paper_shadow/run_day_to_night_option_shadow.py", "e6977bf657e4591fb585b4a8a2209128de11a3fb8a93efd018b223585f16618c"),
        ),
        execution_scope="PAPER_SHADOW_READ_ONLY",
        unresolved_requirements=(
            "active_futures_contract_identity_not_bound_to_health_evidence",
            "dynamic_option_contract_identity_not_bound_to_health_evidence",
            "quote_window_is_causal_bounded_but_no_identity_scoped_freshness_policy_exists",
            "paper_shadow_runner_is_not_paper_execution_authority",
        ),
    ),
    CandidateFeedDependencySpec(
        candidate_id="DAY_TO_NIGHT_MOMENTUM_V1",
        authority_status=PARTIAL_DECLARATION,
        required_domains=(),
        required_identities=(),
        source_sha256=(("core/paper_shadow/run_day_to_night_shadow.py", "ede15c3f6d83542bc962ad5024d4ac00a92a7ae94de5a197d3edbf78f020b8a3"),),
        execution_scope="UNVERIFIED",
        unresolved_requirements=(
            "no_versioned_frozen_spec_contract_found",
            "candidate_inputs_identity_optional_fallback_and_freshness_not_governed",
            "paper_shadow_runner_is_not_paper_execution_authority",
        ),
    ),
    *tuple(
        CandidateFeedDependencySpec(
            candidate_id=candidate_id,
            authority_status=PARTIAL_DECLARATION,
            required_domains=("INDEX_SPOT", "INDEX_FUTURES"),
            required_identities=(("INDEX_SPOT", None), ("INDEX_FUTURES", None)),
            source_sha256=(
                ("core/candidate_evaluators.py", "073e1dcdfb4d46033deb3ae6f24b6c9126878c981d05617e21ff4b1e17322b46"),
                ("core/market_session_store.py", "5482d74a3255fbb0510485996944253c6f91634a2aaab2b0c5504733725a6db9"),
                ("core/orchestrator.py", "f14daf71f06dadc29847eac17f2b2472d1be7e6e5ad520a4b23a906a19251efd"),
                ("core/governed_strategy_authority.py", "54d08ecc0fe676875e46b26c87ab00bf1cc07f026b245a4c198013793c5e18fc"),
            ),
            execution_scope="GOVERNED_CANDIDATE_WITH_UNVERIFIED_FEED_BINDING",
            unresolved_requirements=(
                "market_memory_symbol_not_bound_to_authoritative_feed_identity",
                "futures_entry_exit_identity_not_bound_to_health_evidence",
                "generic_market_data_fallback_can_synthesize_memory_without_source_identity",
                "freshness_watermark_is_not_age_bounded",
            ),
            optional_domains=(),
            fallback_inputs=("generic_market_data_to_synthetic_MarketMemorySnapshot_when_session_store_missing",),
            breadth_inputs=(),
            freshness_policy=("rejects_nonpositive_freshness_watermark; no timestamp-age SLA",),
        )
        for candidate_id in (
            "C1_INTRADAY_15M_IMPULSE",
            "ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
            "C1",
            "C2_OVERNIGHT_TREND",
            "ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
            "C2",
        )
    ),
    CandidateFeedDependencySpec(
        candidate_id="nifty_intraday",
        authority_status=PARTIAL_DECLARATION,
        required_domains=(),
        required_identities=(),
        source_sha256=(("strategies/nifty_intraday.py", "86f0aff6e0e893cb6e39886502a74c7abb23796264a52da01e134abdac11a31e"),),
        execution_scope="UNVERIFIED",
        unresolved_requirements=(
            "strategy_contract_inputs_are_coarse_labels_NIFTY_SPOT_AND_NIFTY_OPTIONS",
            "canonical_domain_mapping_and_freshness_are_undeclared",
        ),
    ),
    CandidateFeedDependencySpec(
        candidate_id="banknifty_intraday",
        authority_status=PARTIAL_DECLARATION,
        required_domains=(),
        required_identities=(),
        source_sha256=(("strategies/banknifty_intraday.py", "945f53c68ab33933f21ef692a335581e78df2f12f9433edcc7515597b5fd252b"),),
        execution_scope="UNVERIFIED",
        unresolved_requirements=(
            "strategy_contract_inputs_are_coarse_labels_BANKNIFTY_SPOT_AND_BANKNIFTY_OPTIONS",
            "canonical_domain_mapping_and_freshness_are_undeclared",
        ),
    ),
)


def validate_registry_entries(
    entries: Iterable[CandidateFeedDependencySpec] = REGISTRY_ENTRIES,
    *,
    current_source_digests: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return stable registry-integrity errors; an empty tuple means valid."""
    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, CandidateFeedDependencySpec):
            errors.append("REGISTRY_ENTRY_MALFORMED")
            continue
        if not isinstance(entry.candidate_id, str):
            errors.append("REGISTRY_CANDIDATE_ID_MALFORMED")
            continue
        candidate_id = entry.candidate_id.strip()
        if not candidate_id:
            errors.append("REGISTRY_CANDIDATE_ID_MISSING")
        elif candidate_id in seen:
            errors.append("REGISTRY_DUPLICATE_CANDIDATE_ID")
        seen.add(candidate_id)
        if not isinstance(entry.authority_status, str) or entry.authority_status not in _VALID_AUTHORITY_STATUSES:
            errors.append("REGISTRY_AUTHORITY_STATUS_INVALID")
        if not isinstance(entry.required_domains, tuple) or any(
            not isinstance(domain, str) or domain not in _VALID_DOMAINS
            for domain in entry.required_domains
        ):
            errors.append("REGISTRY_REQUIRED_DOMAIN_INVALID")
        if not isinstance(entry.required_identities, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or item[0] not in _VALID_DOMAINS
            or (item[1] is not None and not isinstance(item[1], str))
            for item in entry.required_identities
        ):
            errors.append("REGISTRY_REQUIRED_IDENTITY_DOMAIN_INVALID")
        if not isinstance(entry.source_sha256, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
            for item in entry.source_sha256
        ):
            errors.append("REGISTRY_SOURCE_DIGEST_MALFORMED")
            continue
        if len({path for path, _ in entry.source_sha256}) != len(entry.source_sha256):
            errors.append("REGISTRY_SOURCE_PATH_DUPLICATE")
        for path, expected in entry.source_sha256:
            if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
                errors.append("REGISTRY_SOURCE_DIGEST_INVALID")
                continue
            actual = (
                current_source_digests.get(path)
                if current_source_digests is not None
                else _current_source_digest(path)
            )
            if actual != expected:
                errors.append("REGISTRY_SOURCE_DIGEST_MISMATCH")
        if not isinstance(entry.execution_scope, str) or not isinstance(entry.unresolved_requirements, tuple) or any(
            not isinstance(item, str) for item in entry.unresolved_requirements
        ):
            errors.append("REGISTRY_EXECUTION_METADATA_MALFORMED")
        for field_name in ("optional_domains", "fallback_inputs", "breadth_inputs", "freshness_policy"):
            value = getattr(entry, field_name)
            if value is not None and (
                not isinstance(value, tuple)
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                errors.append("REGISTRY_OPTIONAL_FALLBACK_FRESHNESS_METADATA_MALFORMED")
    return tuple(dict.fromkeys(errors))


@lru_cache(maxsize=64)
def _current_source_digest(relative_path: str) -> str | None:
    root = Path(__file__).resolve().parents[1]
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def resolve_candidate_dependencies(
    candidate_id: str | None,
    *,
    caller_required_domains: object = None,
    identity_health_by_identity: object = None,
) -> CandidateDependencyResolution:
    normalized = str(candidate_id or "").strip()
    if not normalized:
        return CandidateDependencyResolution(
            status=UNKNOWN_BLOCKED,
            reason="CANDIDATE_FEED_DEPENDENCY_ID_MISSING",
            candidate_id=None,
        )
    errors = validate_registry_entries()
    if errors:
        return CandidateDependencyResolution(
            status=UNKNOWN_BLOCKED,
            reason="CANDIDATE_FEED_DEPENDENCY_REGISTRY_INVALID:" + ",".join(errors),
            candidate_id=normalized,
        )
    entry = next((item for item in REGISTRY_ENTRIES if item.candidate_id == normalized), None)
    if entry is None:
        return CandidateDependencyResolution(
            status=UNKNOWN_BLOCKED,
            reason="CANDIDATE_FEED_DEPENDENCY_ID_UNKNOWN",
            candidate_id=normalized,
        )
    if not isinstance(caller_required_domains, (list, tuple)):
        if entry.required_domains:
            return _resolution_from_entry(entry, "CANDIDATE_FEED_DEPENDENCY_DECLARATION_MISSING")
    elif tuple(caller_required_domains) != entry.required_domains:
        return _resolution_from_entry(entry, "CANDIDATE_FEED_DEPENDENCY_DECLARATION_MISMATCH")
    if entry.authority_status != VERIFIED_DECLARATION:
        return _resolution_from_entry(entry, "CANDIDATE_FEED_DEPENDENCY_AUTHORITY_INCOMPLETE")
    if not entry.execution_eligible:
        return _resolution_from_entry(entry, "CANDIDATE_FEED_DEPENDENCY_NOT_EXECUTION_AUTHORIZED")
    health = identity_health_by_identity
    if not isinstance(health, Mapping):
        return _resolution_from_entry(entry, "CANDIDATE_FEED_IDENTITY_HEALTH_MISSING")
    for domain, identity in entry.required_identities:
        if identity is None:
            return _resolution_from_entry(entry, "CANDIDATE_FEED_REQUIRED_IDENTITY_UNRESOLVED")
        item = health.get(identity)
        if not isinstance(item, Mapping) or str(item.get("domain", "")).upper() != domain:
            return _resolution_from_entry(entry, "CANDIDATE_FEED_IDENTITY_HEALTH_MISMATCH")
        if str(item.get("state", "")).upper() != "HEALTHY":
            return _resolution_from_entry(entry, "CANDIDATE_FEED_REQUIRED_IDENTITY_NOT_HEALTHY")
    return _resolution_from_entry(entry, "CANDIDATE_FEED_DEPENDENCIES_VERIFIED", eligible=True)


def _resolution_from_entry(
    entry: CandidateFeedDependencySpec,
    reason: str,
    *,
    eligible: bool = False,
) -> CandidateDependencyResolution:
    return CandidateDependencyResolution(
        status=entry.authority_status,
        reason=reason,
        candidate_id=entry.candidate_id,
        required_domains=entry.required_domains,
        required_identities=entry.required_identities,
        source_sha256=entry.source_sha256,
        execution_eligible=eligible and entry.execution_eligible,
        optional_domains=entry.optional_domains,
        fallback_inputs=entry.fallback_inputs,
        breadth_inputs=entry.breadth_inputs,
        freshness_policy=entry.freshness_policy,
    )
