from scripts.validate_frozen_head_bridge import SHA_RE, high_risk


def test_sha_requires_full_length():
    assert SHA_RE.fullmatch("a" * 40)
    assert not SHA_RE.fullmatch("a" * 39)
    assert not SHA_RE.fullmatch("a" * 40 + "0")


def test_high_risk_scope_is_fail_closed():
    assert high_risk("core/feed/runtime_store.py")
    assert not high_risk("docs/governance/readme.md")
