from scripts.release_manager_mutation_campaign import run_campaign


def test_release_manager_mutation_campaign_detects_all_cases():
    result = run_campaign()

    assert result["pass"] is True
    assert result["release_manager_mutations_detected"] == f"{result['total']}/{result['total']}"
    assert result["mandatory_mutation_classes_detected"] == "15/15"
    assert result["broker_api_called"] is False
    assert result["orders_placed"] == 0
    assert {case["mutation_id"] for case in result["cases"] if case["mutation_id"].startswith("M")} == {
        f"M{number:02d}" for number in range(1, 16)
    }
