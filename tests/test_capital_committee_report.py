from core.capital_allocator import compute_desk_budgets


def test_compute_desk_budgets_no_data():
    report = compute_desk_budgets(days=1, global_capital=100000, desk_db_paths={})
    assert "budgets" in report
    assert report["global_capital"] == 100000
