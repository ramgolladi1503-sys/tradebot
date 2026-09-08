from scripts.independent_morning_readiness_verifier import verify
from scripts.morning_readiness_matrix import run


def test_required_offline_matrix_passes():
    report = run()
    assert report["all_pass"] is True
    assert report["orders_placed"] == 0


def test_independent_verifier_recomputes_pass():
    report = verify()
    assert report["pass"] is True
    assert all(report["checks"].values())
