from pathlib import Path

import yaml


SPEC = Path("research/governance/banknifty_v1/specification.yaml")


def test_banknifty_spec_freezes_causal_target_and_search_boundary():
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    assert spec["task_id"] == "T04"
    assert spec["target"]["label"] == "next_session_open_gap"
    assert spec["causal_cutoff"]["latest_allowed_input"] == "09:14:59"
    assert spec["splits"]["untouched_oos"].startswith("chronological")
    assert spec["search_accounting"]["outcome_conditioned_tuning"] == "forbidden"
    assert spec["decision"]["positive_result_not_required"] is True


def test_banknifty_spec_is_execution_isolated():
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    for key in ("execution_authority", "broker_write_authority", "order_authority", "paper_authorized", "live_authorized"):
        assert spec["decision"][key] is False
