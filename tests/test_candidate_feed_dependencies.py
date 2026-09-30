from __future__ import annotations

from dataclasses import replace

from core.candidate_feed_dependencies import (
    PARTIAL_DECLARATION,
    REGISTRY_ENTRIES,
    UNKNOWN_BLOCKED,
    CandidateFeedDependencySpec,
    resolve_candidate_dependencies,
    validate_registry_entries,
)


def test_registry_entries_have_unique_ids_valid_schemas_and_current_source_hashes():
    assert validate_registry_entries() == ()
    ids = [entry.candidate_id for entry in REGISTRY_ENTRIES]
    assert len(ids) == len(set(ids))
    assert all(entry.source_sha256 for entry in REGISTRY_ENTRIES)


def test_partial_opening_drive_dependency_blocks_even_when_domains_are_healthy():
    result = resolve_candidate_dependencies(
        "INTRADAY_OPENING_DRIVE_V1",
        caller_required_domains=["INDEX_SPOT", "INDEX_FUTURES", "INDEX_OPTIONS"],
        identity_health_by_identity={
            "NIFTY 50": {"domain": "INDEX_SPOT", "state": "HEALTHY"}
        },
    )
    assert result.status == PARTIAL_DECLARATION
    assert result.execution_eligible is False
    assert result.reason == "CANDIDATE_FEED_DEPENDENCY_AUTHORITY_INCOMPLETE"
    assert ("INDEX_FUTURES", None) in result.required_identities


def test_registry_rejects_caller_domain_widening_or_narrowing():
    result = resolve_candidate_dependencies(
        "INTRADAY_OPENING_DRIVE_V1",
        caller_required_domains=["INDEX_SPOT", "INDEX_OPTIONS"],
    )
    assert result.execution_eligible is False
    assert result.reason == "CANDIDATE_FEED_DEPENDENCY_DECLARATION_MISMATCH"


def test_advisory_and_historical_candidate_ids_never_gain_execution_authority():
    advisory = resolve_candidate_dependencies(
        "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1",
        caller_required_domains=["INDEX_SPOT"],
        identity_health_by_identity={"NIFTY": {"domain": "INDEX_SPOT", "state": "HEALTHY"}},
    )
    historical = resolve_candidate_dependencies(
        "S1_MOMENTUM_OVERNIGHT_V1",
        caller_required_domains=["INDEX_SPOT"],
        identity_health_by_identity={"NIFTY50": {"domain": "INDEX_SPOT", "state": "HEALTHY"}},
    )
    assert advisory.execution_eligible is False
    assert advisory.reason == "CANDIDATE_FEED_DEPENDENCY_NOT_EXECUTION_AUTHORIZED"
    assert historical.execution_eligible is False
    assert historical.status == PARTIAL_DECLARATION


def test_unknown_and_missing_candidate_ids_fail_closed():
    unknown = resolve_candidate_dependencies("UNREGISTERED_MOVEMENT_FAMILY")
    missing = resolve_candidate_dependencies(None)
    assert unknown.status == UNKNOWN_BLOCKED
    assert unknown.reason == "CANDIDATE_FEED_DEPENDENCY_ID_UNKNOWN"
    assert missing.status == UNKNOWN_BLOCKED
    assert missing.reason == "CANDIDATE_FEED_DEPENDENCY_ID_MISSING"


def test_duplicate_malformed_and_stale_digest_registry_entries_fail_closed():
    entry = REGISTRY_ENTRIES[1]
    duplicate = validate_registry_entries((entry, entry))
    malformed = validate_registry_entries((replace(entry, authority_status="PASS"),))
    malformed_schema = validate_registry_entries((replace(entry, required_domains=["INDEX_SPOT"]),))
    stale = validate_registry_entries(
        (entry,),
        current_source_digests={path: "f" * 64 for path, _ in entry.source_sha256},
    )
    assert "REGISTRY_DUPLICATE_CANDIDATE_ID" in duplicate
    assert "REGISTRY_AUTHORITY_STATUS_INVALID" in malformed
    assert "REGISTRY_REQUIRED_DOMAIN_INVALID" in malformed_schema
    assert "REGISTRY_SOURCE_DIGEST_MISMATCH" in stale


def test_registry_spec_is_frozen_and_unknown_optional_inputs_are_not_invented():
    assert isinstance(REGISTRY_ENTRIES, tuple)
    assert all(isinstance(entry, CandidateFeedDependencySpec) for entry in REGISTRY_ENTRIES)
    assert all(not entry.execution_eligible for entry in REGISTRY_ENTRIES)
    assert all(entry.unresolved_requirements for entry in REGISTRY_ENTRIES)


def test_all_discovered_day_to_night_shadow_ids_are_registered_and_blocked():
    by_id = {entry.candidate_id: entry for entry in REGISTRY_ENTRIES}
    for candidate_id in (
        "DAY_TO_NIGHT_MOMENTUM_V1",
        "DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION",
    ):
        assert candidate_id in by_id
        assert by_id[candidate_id].authority_status == PARTIAL_DECLARATION
        assert by_id[candidate_id].execution_eligible is False
        result = resolve_candidate_dependencies(candidate_id)
        assert result.status == PARTIAL_DECLARATION
        assert result.execution_eligible is False


def test_day_to_night_option_contract_records_frozen_domains_but_unresolved_identities():
    entry = next(
        item for item in REGISTRY_ENTRIES
        if item.candidate_id == "DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION"
    )
    assert entry.required_domains == ("INDEX_FUTURES", "INDEX_SPOT", "INDEX_OPTIONS")
    assert ("INDEX_FUTURES", None) in entry.required_identities
    assert ("INDEX_OPTIONS", None) in entry.required_identities
    assert any("freshness_policy" in item for item in entry.unresolved_requirements)
    assert entry.optional_domains is None
    assert entry.fallback_inputs is None
    assert entry.breadth_inputs is None
    assert entry.freshness_policy is None
    result = resolve_candidate_dependencies(entry.candidate_id)
    payload = result.to_payload()
    assert payload["optional_domains"] is None
    assert payload["fallback_inputs"] is None
    assert payload["breadth_inputs"] is None
    assert payload["freshness_policy"] is None


def test_undeclared_optional_fallback_breadth_or_freshness_cannot_be_encoded_as_malformed_empty_values():
    entry = REGISTRY_ENTRIES[0]
    malformed = replace(entry, optional_domains=["INDEX_OPTIONS"])
    errors = validate_registry_entries((malformed,))
    assert "REGISTRY_OPTIONAL_FALLBACK_FRESHNESS_METADATA_MALFORMED" in errors


def test_c1_c2_aliases_and_emitted_candidate_ids_are_covered_but_fail_closed():
    by_id = {entry.candidate_id: entry for entry in REGISTRY_ENTRIES}
    aliases = (
        "C1_INTRADAY_15M_IMPULSE",
        "ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE",
        "C1",
        "C2_OVERNIGHT_TREND",
        "ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT",
        "C2",
    )
    assert all(candidate_id in by_id for candidate_id in aliases)
    for candidate_id in aliases:
        entry = by_id[candidate_id]
        assert entry.required_domains == ("INDEX_SPOT", "INDEX_FUTURES")
        assert entry.required_identities == (("INDEX_SPOT", None), ("INDEX_FUTURES", None))
        assert entry.execution_eligible is False
        result = resolve_candidate_dependencies(candidate_id)
        assert result.status == PARTIAL_DECLARATION
        assert result.execution_eligible is False
    c1 = by_id[aliases[0]]
    assert c1.optional_domains == ()
    assert c1.breadth_inputs == ()
    assert c1.fallback_inputs is not None
    assert c1.freshness_policy is not None
