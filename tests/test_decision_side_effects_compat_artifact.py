from core.decision_side_effects import _INDICATOR_MISSING_COMPAT_PATH


def test_missing_indicator_compatibility_artifact_is_not_authoritative_latest():
    assert _INDICATOR_MISSING_COMPAT_PATH.name == "indicator_missing_runtime_latest.json"
    assert _INDICATOR_MISSING_COMPAT_PATH.name != "live_indicator_readiness_latest.json"
