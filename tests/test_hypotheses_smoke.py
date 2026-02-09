from core.hypothesis_engine import generate_hypotheses


def test_generate_hypotheses_returns_list():
    result = generate_hypotheses()
    assert isinstance(result, list)
