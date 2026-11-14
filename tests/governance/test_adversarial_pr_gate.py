from scripts import run_adversarial_pr_gate as gate


def test_attack_classifier_covers_all_non_test_python_and_critical_non_python():
    for path in (
        "main.py",
        "config/config.py",
        "dashboard/app.py",
        "patch_watchdog.py",
        "research/foo.py",
        "scripts/helper.py",
        "test_disguised_production.py",
    ):
        assert gate._is_code(path)
        assert gate._requires_attack(path)
    for path in (
        "requirements.txt",
        "pyproject.toml",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        ".github/workflows/ci.yml",
    ):
        assert gate._requires_attack(path)
    assert not gate._requires_attack("docs/guide.md")


def test_only_canonical_tests_tree_counts_as_test_evidence():
    assert gate._is_test("tests/test_x.py")
    assert gate._is_test("tests/research/foo_safety.py")
    assert not gate._is_test("test_root_helper.py")
    assert not gate._is_test("tools/test_disguised_production.py")
    assert gate._is_code("test_root_helper.py")
    assert gate._is_code("tools/test_disguised_production.py")


def test_high_risk_classifier_covers_execution_and_governance():
    for path in (
        "main.py",
        "core/execution_engine.py",
        "core/risk_engine.py",
        "core/feed/supervisor.py",
        "strategies/foo.py",
        ".github/workflows/ci.yml",
    ):
        assert gate._high_risk(path)
    assert not gate._high_risk("docs/readme.md")


def test_attack_required_change_without_tests_fails_closed():
    errors = []
    gate._coverage_shape_attack(["core/foo.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_TEST_CHANGE" in errors
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_happy_path_test_only_is_not_adversarial_evidence():
    errors = []
    gate._coverage_shape_attack(["dashboard/widget.py", "tests/test_widget.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_high_risk_change_requires_adversarial_named_test():
    errors = []
    gate._coverage_shape_attack(["core/risk_guard.py", "tests/test_risk_guard.py"], errors)
    assert "HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_gate_bootstrap_cannot_be_reused_or_smuggle_other_governance(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: False)
    errors = []
    gate._governance_self_protection(
        "base", list(gate.BOOTSTRAP_ALLOWED_PATHS), gate.BOOTSTRAP_BRANCH, errors
    )
    assert errors == []

    errors = []
    gate._governance_self_protection(
        "base", [".github/workflows/ci.yml"], gate.BOOTSTRAP_BRANCH, errors
    )
    assert errors == ["BOOTSTRAP_SCOPE_VIOLATION:.github/workflows/ci.yml"]

    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: True)
    errors = []
    gate._governance_self_protection(
        "base", list(gate.BOOTSTRAP_ALLOWED_PATHS), gate.BOOTSTRAP_BRANCH, errors
    )
    assert errors
    assert errors[0].startswith("ADVERSARIAL_GATE_SELF_MODIFICATION_BLOCKED")


def test_ordinary_pr_cannot_modify_gate_or_required_ci(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: True)
    for protected in (
        "scripts/run_adversarial_pr_gate.py",
        ".github/workflows/adversarial-pr-gate.yml",
        ".github/workflows/ci.yml",
        "tests/governance/test_adversarial_pr_gate_workflow_safety.py",
    ):
        errors = []
        gate._governance_self_protection("base", [protected], "feature/x", errors)
        assert errors


def test_syntax_attack_detects_invalid_python(monkeypatch):
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: "def broken(:\n    pass\n")
    errors = []
    gate._syntax_attack("candidate", ["dashboard/app.py"], errors)
    assert errors
    assert errors[0].startswith("SYNTAX_ATTACK_FAIL:dashboard/app.py")


def test_dynamic_execution_attack_detects_direct_and_indirect_added_calls(monkeypatch):
    diff = "\n".join(
        [
            "@@ -0,0 +1,5 @@",
            "+eval('1+1')",
            "+exec('x=1')",
            "+compile('x=1', '<x>', 'exec')",
            "+__import__('os')",
            "+fn = getattr(builtins, 'eval')",
        ]
    )
    monkeypatch.setattr(gate, "changed_diff", lambda base, candidate, path: diff)
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["dashboard/app.py"], errors)
    assert len(errors) == 5
    assert any(e.startswith("DANGEROUS_API_INDIRECT_LOOKUP_ADDED") for e in errors)


def test_preexisting_dynamic_execution_is_not_misreported_as_new(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: "@@ -1 +1 @@\n compile(existing, '<x>', 'exec')\n+safe_call()",
    )
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["core/foo.py"], errors)
    assert errors == []


def test_skip_and_xfail_weakening_attacks_are_detected(monkeypatch):
    for added in (
        "+@pytest.mark.skip(reason='hide')",
        "+pytest.skip('hide')",
        "+pytest.xfail('hide')",
        "+@pytest.mark.xfail(reason='hide')",
    ):
        monkeypatch.setattr(
            gate,
            "changed_diff",
            lambda base, candidate, path, line=added: f"@@ -0,0 +1 @@\n{line}",
        )
        errors = []
        gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
        assert any(e.startswith("TEST_WEAKENING_SKIP_OR_XFAIL_ADDED") for e in errors)


def test_trivial_assert_and_broad_exception_weakening_are_detected(monkeypatch):
    diff = "@@ -0,0 +1,2 @@\n+assert True\n+with pytest.raises(Exception):"
    monkeypatch.setattr(gate, "changed_diff", lambda base, candidate, path: diff)
    errors = []
    gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
    assert any(e.startswith("TEST_WEAKENING_TRIVIAL_ASSERT_ADDED") for e in errors)
    assert any(e.startswith("TEST_WEAKENING_BROAD_EXCEPTION_ASSERTION") for e in errors)


def test_assertion_removal_without_replacement_is_detected(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: "@@ -1 +1 @@\n-    assert result is False\n+    result",
    )
    errors = []
    gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
    assert any(e.startswith("TEST_WEAKENING_ASSERTION_LOSS") for e in errors)


def test_pytest_collection_suppression_is_blocked(monkeypatch):
    for added in (
        "+addopts = --ignore=tests/integration",
        "+addopts = --deselect=tests/test_x.py::test_bad",
        "+testpaths = tests/small_subset",
        "+python_files = test_only_easy_cases.py",
    ):
        monkeypatch.setattr(
            gate,
            "changed_diff",
            lambda base, candidate, path, line=added: f"@@ -0,0 +1 @@\n{line}",
        )
        errors = []
        gate._pytest_config_suppression_attack("base", "candidate", ["pyproject.toml"], errors)
        assert errors
        assert errors[0].startswith("PYTEST_COLLECTION_OR_SUPPRESSION_CHANGE_REQUIRES_EXPLICIT_RECERTIFICATION")


def test_pass_only_and_trivial_adversarial_tests_are_rejected(monkeypatch):
    for body in ("pass", "assert True", "assert result == result"):
        source = f"def test_attack_rejects_bad_input():\n    {body}\n"
        monkeypatch.setattr(gate, "_read_candidate", lambda ref, path, src=source: src)
        errors = []
        gate._adversarial_test_quality_attack(
            "candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors
        )
        assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_broad_pytest_raises_does_not_count_as_substantive(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    with pytest.raises(Exception):\n        dangerous()\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors
    )
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_high_risk_requires_multiple_substantive_negative_cases(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    assert value is False\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate", ["core/risk_guard.py", "tests/test_risk_guard_adversarial.py"], errors
    )
    assert any(e.startswith("ADVERSARIAL_TEST_TOO_SHALLOW") for e in errors)
    assert any(e.startswith("ADVERSARIAL_TEST_SUBSTANTIVE_CASE_FLOOR_FAIL") for e in errors)


def test_two_substantive_high_risk_negative_cases_clear_quality_floor(monkeypatch):
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
        "candidate", ["core/risk_guard.py", "tests/test_risk_guard_adversarial.py"], errors
    )
    assert errors == []


def test_adversarial_test_name_must_be_inside_tests_tree():
    assert gate._is_adversarial_test("tests/test_order_safety.py")
    assert gate._is_adversarial_test("tests/test_math_negative.py")
    assert not gate._is_adversarial_test("tools/test_fake_safety.py")
    assert not gate._is_adversarial_test("tests/test_happy_path.py")
