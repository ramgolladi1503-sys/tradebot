from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.candidate_outcome_fixture_loader import (
    CandidateOutcomeFixture,
    evaluate_candidate_outcome_fixture,
    load_candidate_outcome_fixture,
    load_candidate_outcome_fixtures,
)
from core.candidate_outcome_truth import (
    AMBIGUOUS_SAME_BAR,
    NO_OBSERVATIONS,
    NOT_EXECUTABLE,
    STOP_HIT,
    TARGET_HIT,
    TIMEOUT,
    CandidateOutcomeInput,
    PriceObservation,
)


FIXTURE_DIR = Path("tests/fixtures/candidate_outcomes")


def test_load_single_target_hit_fixture() -> None:
    fixture = load_candidate_outcome_fixture(FIXTURE_DIR / "target_hit.json")

    assert fixture.fixture_id == "target_hit"
    assert isinstance(fixture.candidate, CandidateOutcomeInput)
    assert fixture.candidate.symbol == "NIFTY"
    assert fixture.observations == (
        PriceObservation(observed_epoch=101.0, ltp=103.0),
        PriceObservation(observed_epoch=102.0, ltp=110.0),
    )

    truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / "target_hit.json")
    assert truth.outcome_status == TARGET_HIT


def test_load_stop_hit_fixture() -> None:
    truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / "stop_hit.json")
    assert truth.outcome_status == STOP_HIT


def test_load_timeout_fixture() -> None:
    truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / "timeout.json")
    assert truth.outcome_status == TIMEOUT


def test_load_not_executable_fixture() -> None:
    truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / "not_executable.json")
    assert truth.outcome_status == NOT_EXECUTABLE


def test_load_no_observations_fixture() -> None:
    truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / "no_observations.json")
    assert truth.outcome_status == NO_OBSERVATIONS


def test_load_ambiguous_same_bar_fixture() -> None:
    truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / "ambiguous_same_bar.json")
    assert truth.outcome_status == AMBIGUOUS_SAME_BAR


def test_post_timeout_target_ignored_fixture() -> None:
    truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / "post_timeout_target_ignored.json")

    assert truth.outcome_status == TIMEOUT
    assert truth.target_hit is False
    assert truth.first_hit_epoch is None
    assert truth.observation_count == 1
    assert math.isclose(truth.gross_r, 0.8)


def test_load_directory_is_deterministic() -> None:
    fixtures = load_candidate_outcome_fixtures(FIXTURE_DIR)

    assert [fixture.fixture_id for fixture in fixtures] == sorted(
        fixture.fixture_id for fixture in fixtures
    )


def test_missing_directory_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="fixture directory does not exist"):
        load_candidate_outcome_fixtures(missing)


def test_malformed_fixture_fails_closed(tmp_path: Path) -> None:
    fixture_path = tmp_path / "malformed.json"
    fixture_path.write_text(
        """{"schema_version": 1, "fixture_id": "bad", "observations": []}"""
    )

    with pytest.raises(ValueError, match="fixture field 'candidate' must be an object"):
        load_candidate_outcome_fixture(fixture_path)


def test_expected_outcome_status_matches_fixture() -> None:
    for fixture in load_candidate_outcome_fixtures(FIXTURE_DIR):
        truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / f"{fixture.fixture_id}.json")
        assert truth.outcome_status == fixture.expected_outcome_status


def test_fixture_evaluation_preserves_read_only_flags() -> None:
    for fixture in load_candidate_outcome_fixtures(FIXTURE_DIR):
        truth = evaluate_candidate_outcome_fixture(FIXTURE_DIR / f"{fixture.fixture_id}.json")
        payload = truth.to_payload()
        assert payload["read_only"] is True
        assert payload["append"] is False
        assert payload["is_order_action"] is False
        assert payload["broker_api_called"] is False
        assert payload["live_order_allowed"] is False
        assert payload["live_order_action"] is False
        assert payload["broker_order_action"] is False


def test_fixture_loader_preserves_metadata() -> None:
    fixture = load_candidate_outcome_fixture(FIXTURE_DIR / "target_hit.json")
    assert fixture.metadata["closed_environment"] is True
    assert fixture.metadata["source"] == "synthetic"

