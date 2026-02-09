from scripts.paper_tournament import _compute_stats


def test_compute_stats_empty():
    stats = _compute_stats([])
    assert stats["trades"] == 0
    assert stats["expectancy"] == 0.0
