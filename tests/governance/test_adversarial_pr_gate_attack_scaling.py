from scripts import run_adversarial_pr_gate as gate


def test_attack_depth_scales_with_number_of_changed_surfaces(monkeypatch):
    changed = [f"dashboard/module_{i}.py" for i in range(9)]
    changed.append("tests/test_generic_attack.py")
    source = "\n".join(
        [
            "def test_attack_case_one():",
            "    assert blocked is True",
            "",
            "def test_negative_case_two():",
            "    assert allowed is False",
        ]
    )
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", changed, errors)
    assert gate._required_attack_case_count(changed[:-1], high_risk=False) == 3
    assert any(e.startswith("ADVERSARIAL_TEST_TOO_SHALLOW") for e in errors)
    assert any(e.startswith("ADVERSARIAL_TEST_SUBSTANTIVE_CASE_FLOOR_FAIL") for e in errors)


def test_high_risk_generic_attack_does_not_count_as_surface_coverage(monkeypatch):
    source = "\n".join(
        [
            "import core.unrelated",
            "",
            "def test_attack_rejects_bad_input():",
            "    assert rejected is True",
            "",
            "def test_boundary_blocks_missing_authority():",
            "    assert allowed is False",
        ]
    )
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate",
        ["core/risk_guard.py", "tests/test_generic_attack.py"],
        errors,
    )
    assert "HIGH_RISK_SURFACE_UNREFERENCED_BY_ADVERSARIAL_TEST:core/risk_guard.py" in errors


def test_high_risk_imported_module_is_linked_to_adversarial_evidence(monkeypatch):
    source = "\n".join(
        [
            "import core.risk_guard",
            "",
            "def test_attack_rejects_bad_input():",
            "    assert rejected is True",
            "",
            "def test_boundary_blocks_missing_authority():",
            "    assert allowed is False",
        ]
    )
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate",
        ["core/risk_guard.py", "tests/test_generic_attack.py"],
        errors,
    )
    assert not any(e.startswith("HIGH_RISK_SURFACE_UNREFERENCED") for e in errors)
    assert errors == []


def test_high_risk_test_filename_can_link_surface_without_import(monkeypatch):
    source = "\n".join(
        [
            "def test_attack_rejects_bad_input():",
            "    assert rejected is True",
            "",
            "def test_boundary_blocks_missing_authority():",
            "    assert allowed is False",
        ]
    )
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate",
        ["core/risk_guard.py", "tests/test_risk_guard_attack.py"],
        errors,
    )
    assert not any(e.startswith("HIGH_RISK_SURFACE_UNREFERENCED") for e in errors)
    assert errors == []
