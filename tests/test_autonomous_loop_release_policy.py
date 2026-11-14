from research.governance.autonomous_loop.release_policy import evaluate_program_release


def _policy(**overrides):
    base = {
        "merge_hold_through_task_id": "T37",
        "require_all_tasks_through_hold_sealed": True,
        "require_framework_exact_sha_certification": True,
        "require_program_exact_sha_independent_verification": True,
        "require_program_ci_green": True,
        "require_zero_unresolved_major_critical": True,
        "require_zero_mandatory_unknowns": True,
        "main_merge_authorized": False,
    }
    base.update(overrides)
    return base


def _registry(last=35, status="SEALED"):
    return {
        "tasks": {
            f"T{number:02d}": {"task_id": f"T{number:02d}", "status": status}
            for number in range(1, last + 1)
        }
    }


def _evaluate(registry, policy=None, **overrides):
    args = {
        "framework_certified": True,
        "exact_sha_independently_verified": True,
        "ci_green": True,
        "unresolved_major_critical": 0,
        "mandatory_unknowns": 0,
    }
    args.update(overrides)
    return evaluate_program_release(registry=registry, policy=policy or _policy(), **args)


def test_t37_threshold_does_not_invent_dynamic_tasks():
    decision = _evaluate(_registry(last=35))
    assert decision.eligible is False
    assert decision.reason == "HOLD_RANGE_TASKS_NOT_YET_GOVERNED"
    assert decision.missing_tasks == ("T36", "T37")


def test_t36_only_still_blocks_program_release():
    decision = _evaluate(_registry(last=36))
    assert decision.eligible is False
    assert decision.missing_tasks == ("T37",)


def test_unsealed_task_anywhere_through_t37_blocks_release():
    registry = _registry(last=37)
    registry["tasks"]["T14"]["status"] = "CI_GREEN"
    decision = _evaluate(registry)
    assert decision.eligible is False
    assert decision.reason == "TASKS_THROUGH_HOLD_NOT_SEALED"
    assert decision.unsealed_tasks == ("T14",)


def test_framework_certification_is_required_but_not_merge_authority():
    decision = _evaluate(_registry(last=37), framework_certified=False)
    assert decision.eligible is False
    assert decision.reason == "FRAMEWORK_NOT_CERTIFIED"


def test_red_program_ci_blocks_even_when_all_tasks_are_sealed():
    decision = _evaluate(_registry(last=37), ci_green=False)
    assert decision.eligible is False
    assert decision.reason == "PROGRAM_CI_NOT_GREEN"


def test_unresolved_major_or_critical_blocks_release():
    decision = _evaluate(_registry(last=37), unresolved_major_critical=1)
    assert decision.eligible is False
    assert decision.reason == "UNRESOLVED_MAJOR_CRITICAL"


def test_mandatory_unknown_blocks_release():
    decision = _evaluate(_registry(last=37), mandatory_unknowns=1)
    assert decision.eligible is False
    assert decision.reason == "MANDATORY_UNKNOWNS_REMAIN"


def test_independent_verification_is_exact_program_gate():
    decision = _evaluate(_registry(last=37), exact_sha_independently_verified=False)
    assert decision.eligible is False
    assert decision.reason == "PROGRAM_INDEPENDENT_VERIFICATION_MISSING"


def test_all_technical_gates_still_require_explicit_human_main_merge_authority():
    decision = _evaluate(_registry(last=37))
    assert decision.eligible is False
    assert decision.reason == "HUMAN_MAIN_MERGE_AUTHORITY_REQUIRED"


def test_explicit_merge_authority_can_only_make_fully_sealed_program_eligible():
    decision = _evaluate(_registry(last=37), policy=_policy(main_merge_authorized=True))
    assert decision.eligible is True
    assert decision.reason == "PROGRAM_RELEASE_ELIGIBLE"
