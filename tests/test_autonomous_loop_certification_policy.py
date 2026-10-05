from pathlib import Path

import yaml


POLICY = Path("research/governance/autonomous_loop/CERTIFICATION_POLICY.yaml")


def load_policy():
    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))


def test_policy_preserves_fail_closed_execution_authority():
    policy = load_policy()
    assert policy["schema_version"] == 1
    assert policy["safety"] == {
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }


def test_task_local_gates_are_required_even_when_broad_ci_is_batched():
    policy = load_policy()
    per_task = policy["per_task_execution"]
    assert per_task["broad_repository_ci_required_immediately"] is False
    assert per_task["broad_repository_ci_required_before_seal"] is True
    assert set(per_task["required_before_progression"]) == {
        "focused_tests",
        "adversarial_tests",
        "task_relevant_integration_tests",
        "compile_or_static_checks",
        "scope_and_authority_guards",
    }
    assert "blocks progression immediately" in per_task["failure_rule"]


def test_locked_tasks_are_covered_exactly_once_by_c01_to_c05():
    policy = load_policy()
    covered = []
    for checkpoint in ("C01", "C02", "C03", "C04", "C05"):
        covered.extend(policy["checkpoints"][checkpoint]["tasks"])
    assert covered == [f"T{i:02d}" for i in range(1, 36)]
    assert policy["checkpoints"]["C06"]["tasks"] == "dynamic_T36_plus"


def test_broad_evidence_reuse_is_exact_sha_bound():
    policy = load_policy()
    rule = policy["per_task_execution"]["evidence_reuse_rule"]
    assert "same exact candidate SHA" in rule
    assert "combined changed surface" in rule


def test_final_program_gate_never_auto_merges_main():
    policy = load_policy()
    final_gate = policy["final_program_gate"]
    assert final_gate["merge_to_main"] == "prohibited_until_explicit_user_authorization"
    required = set(final_gate["required"])
    assert "full_repository_regression_pass" in required
    assert "full_ci_pass" in required
    assert "independent_exact_sha_verification_pass" in required
    assert "execution_isolation_pass" in required
