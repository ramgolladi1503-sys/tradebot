from tools.run_research_validation_mutation_campaign_v1 import run_campaign


def test_every_required_research_validation_mutation_is_detected():
    rows = run_campaign()
    assert rows
    missed = [row for row in rows if row["detected"] is not True]
    assert missed == []
