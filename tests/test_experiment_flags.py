from core.feature_flags import load_flags


def test_experiment_flag_present():
    flags = load_flags()
    assert "EXPERIMENT_ID" in flags
