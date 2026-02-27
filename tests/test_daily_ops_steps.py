from scripts import daily_ops


def test_daily_ops_includes_shadow_steps():
    scripts_list = [cmd[0] for cmd, _optional in daily_ops.STEPS]
    assert "scripts/eval_shadow_outcomes.py" in scripts_list
    assert "scripts/report_gate_quality.py" in scripts_list
