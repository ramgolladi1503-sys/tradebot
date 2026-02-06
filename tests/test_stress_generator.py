from core.stress_generator import SyntheticStressGenerator


def test_stress_generator_run():
    gen = SyntheticStressGenerator(block_size=5, vol_scale=1.5)
    returns = [0.001] * 50
    report = gen.run(returns=returns, start_price=100.0, n_steps=20, n_paths=5)
    assert "max_loss" in report
    assert "tail_cvar" in report
    assert "strategy_survivability" in report
