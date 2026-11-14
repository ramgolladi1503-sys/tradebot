import re

from scripts import run_adversarial_pr_gate as gate


def test_negative_trivial_assert_patterns_compile_without_group_errors():
    compiled = [re.compile(pattern) for pattern in gate.TRIVIAL_ASSERT_PATTERNS]
    assert len(compiled) == len(gate.TRIVIAL_ASSERT_PATTERNS)


def test_attack_rejects_literal_truthy_and_literal_string_assertions():
    assert any(re.search(pattern, "assert True") for pattern in gate.TRIVIAL_ASSERT_PATTERNS)
    assert any(re.search(pattern, "assert 1") for pattern in gate.TRIVIAL_ASSERT_PATTERNS)
    assert any(re.search(pattern, "assert 'always true'") for pattern in gate.TRIVIAL_ASSERT_PATTERNS)


def test_attack_does_not_classify_runtime_boolean_assertion_as_literal_triviality():
    assert not any(re.search(pattern, "assert result is False") for pattern in gate.TRIVIAL_ASSERT_PATTERNS)
