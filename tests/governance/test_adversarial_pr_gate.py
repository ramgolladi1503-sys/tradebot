from scripts import run_adversarial_pr_gate as gate


def test_high_risk_classification_covers_execution_risk_strategies_and_workflows():
    assert gate._high_risk("main.py")
    assert gate._high_risk("core/execution_engine.py")
    assert gate._high_risk("core/risk_engine.py")
    assert gate._high_risk("core/feed/supervisor.py")
    assert gate._high_risk("strategies/foo.py")
    assert gate._high_risk(".github/workflows/ci.yml")
    assert not gate._high_risk("docs/readme.md")


def test_all_non_test_python_surfaces_require_attack():
    for path in (
        "main.py",
        "config/config.py",
        "dashboard/app.py",
        "patch_watchdog.py",
        "research/foo.py",
        "scripts/helper.py",
    ):
        assert gate._is_code(path)
        assert gate._requires_attack(path)
    assert not gate._is_code("tests/test_x.py")


def test_dependency_workflow_and_pytest_config_changes_require_attack_evidence():
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


def test_attack_required_change_without_test_change_fails():
    errors = []
    gate._coverage_shape_attack(["core/foo.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_TEST_CHANGE" in errors
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_low_risk_production_change_still_requires_adversarial_test():
    errors = []
    gate._coverage_shape_attack(["dashboard/widget.py", "tests/test_widget.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_high_risk_change_requires_adversarial_named_test():
    errors = []
    gate._coverage_shape_attack(["core/risk_guard.py", "tests/test_risk_guard.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors
    assert "HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_adversarial_file_name_satisfies_shape_but_not_quality_by_itself():
    errors = []
    gate._coverage_shape_attack(["core/risk_guard.py", "tests/test_risk_guard_attack.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" not in errors


def test_gate_self_modification_fails_outside_bootstrap(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: False)
    errors = []
    gate._governance_self_protection(
        "base", ["scripts/run_adversarial_pr_gate.py"], "feature/ordinary-change", errors
    )
    assert errors


def test_initial_bootstrap_allows_only_bootstrap_files(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: False)
    errors = []
    gate._governance_self_protection(
        "base", list(gate.BOOTSTRAP_ALLOWED_PATHS), gate.BOOTSTRAP_BRANCH, errors
    )
    assert errors == []


def test_bootstrap_cannot_smuggle_required_ci_workflow_change(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: False)
    errors = []
    gate._governance_self_protection(
        "base", [".github/workflows/ci.yml"], gate.BOOTSTRAP_BRANCH, errors
    )
    assert errors == ["BOOTSTRAP_SCOPE_VIOLATION:.github/workflows/ci.yml"]


def test_reusing_bootstrap_branch_after_gate_exists_is_blocked(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: True)
    errors = []
    gate._governance_self_protection(
        "base", list(gate.BOOTSTRAP_ALLOWED_PATHS), gate.BOOTSTRAP_BRANCH, errors
    )
    assert errors


def test_syntax_attack_detects_invalid_python(monkeypatch):
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: "def broken(:\n    pass\n")
    errors = []
    gate._syntax_attack("candidate", ["dashboard/app.py"], errors)
    assert errors and errors[0].startswith("SYNTAX_ATTACK_FAIL:dashboard/app.py")


def test_dangerous_api_attack_detects_direct_and_indirect_calls(monkeypatch):
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


def test_preexisting_dangerous_call_does_not_fail_if_not_added(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: "@@ -1 +1 @@\n compile(existing, '<x>', 'exec')\n+safe_call()",
    )
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["core/foo.py"], errors)
    assert errors == []


def test_added_skip_and_xfail_forms_are_detected(monkeypatch):
    for added in (
        "+@pytest.mark.skip(reason='hide failure')",
        "+pytest.skip('hide failure')",
        "+pytest.xfail('hide failure')",
        "+@pytest.mark.xfail(reason='hide failure')",
    ):
        monkeypatch.setattr(gate, "changed_diff", lambda base, candidate, path, line=added: f"@@ -0,0 +1 @@\n{line}")
        errors = []
        gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
        assert any(e.startswith("TEST_WEAKENING_SKIP_OR_XFAIL_ADDED") for e in errors)


def test_trivial_assertion_and_broad_exception_are_detected(monkeypatch):
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


def test_pytest_collection_suppression_changes_are_blocked(monkeypatch):
    for added in (
        "+addopts = --ignore=tests/integration",
        "+addopts = --deselect=tests/test_x.py::test_bad",
        "+testpaths = tests/small_subset",
        "+python_files = test_only_easy_cases.py",
    ):
        monkeypatch.setattr(gate, "changed_diff", lambda base, candidate, path, line=added: f"@@ -0,0 +1 @@\n{line}")
        errors = []
        gate._pytest_config_suppression_attack("base", "candidate", ["pyproject.toml"], errors)
        assert any(e.startswith("PYTEST_COLLECTION_OR_SUPPRESSION_CHANGE_REQUIRES_EXPLICIT_RECERTIFICATION") for e in errors)


def test_adversarial_file_with_pass_only_is_rejected(monkeypatch):
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: "def test_attack_rejects_bad_input():\n    pass\n")
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors)
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_assert_true_and_self_equality_do_not_satisfy_quality_floor(monkeypatch):
    for assertion in ("assert True", "assert result == result"):
        source = f"def test_attack_rejects_bad_input():\n    {assertion}\n"
        monkeypatch.setattr(gate, "_read_candidate", lambda ref, path, src=source: src)
        errors = []
        gate._adversarial_test_quality_attack("candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors)
        assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_broad_pytest_raises_does_not_count_as_substantive(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    with pytest.raises(Exception):\n        dangerous()\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors)
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_high_risk_change_requires_multiple_substantive_adversarial_checks(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    assert value is False\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/risk_guard.py", "tests/test_risk_guard_adversarial.py"], errors)
    assert any(e.startswith("ADVERSARIAL_TEST_TOO_SHALLOW") for e in errors)
    assert any(e.startswith("ADVERSARIAL_TEST_SUBSTANTIVE_CASE_FLOOR_FAIL") for e in errors)


def test_two_substantive_high_risk_cases_pass_quality_floor(monkeypatch):
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
    gate._adversarial_test_quality_attack("candidate", ["core/risk_guard.py", "tests/test_risk_guard_adversarial.py"], errors)
    assert errors == []


def test_docs_only_change_does_not_require_test_change():
    errors = []
    gate._coverage_shape_attack(["docs/guide.md"], errors)
    assert errors == []


def test_test_files_are_not_classified_as_production_code():
    assert gate._is_test("tests/test_x.py")
    assert gate._is_test("test_root_helper.py")
    assert not gate._is_code("tests/test_x.py")
    assert not gate._requires_attack("tests/test_x.py")


def test_adversarial_test_name_detection_is_explicit():
    assert gate._is_adversarial_test("tests/test_order_safety.py")
    assert gate._is_adversarial_test("tests/test_math_negative.py")
    assert not gate._is_adversarial_test("tests/test_happy_path.py")
