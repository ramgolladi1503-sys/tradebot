import json

from core.read_only_sidecar_manager import write_sidecar_health


def test_sidecar_manager_isolated_and_pending(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "schema_version": 1,
        "sidecars": [],
        "policy": {
            "exact_pr_sha_required": True, "order_authority": False,
            "broker_write_authority": False, "canonical_feed_owner_count": 1,
            "failure_isolation": True,
        },
    }))
    payload = write_sidecar_health(
        registry_path=registry, output_path=tmp_path / "health.json",
        main_session_id="s1", source_sha="a" * 40,
    )
    assert payload["pr_sidecars_isolated"] is True
    assert payload["canonical_feed_owner_count"] == 1
    assert payload["broker_order_calls"] == 0
    assert payload["verdict"] == "PENDING"
