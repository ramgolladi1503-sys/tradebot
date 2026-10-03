"""Synthetic-only adapter checks against mock registry; no runtime imports."""
from types import SimpleNamespace

from research.verification_gateway.contracts import ResearchStrategySpec
from research.verification_gateway.registry_bridge import validate_registry_link
from tests.research.test_verification_gateway_contracts import valid_payload


class MockItem:
    def to_payload(self):
        return {"read_only": True, "append": False,
                "is_order_action": False, "broker_api_called": False}


class MockRegistry:
    valid = True

    def get(self, name):
        return MockItem() if name == "existing" else None


def spec(link):
    p = valid_payload()
    p["existing_registry_strategy_id"] = link
    return ResearchStrategySpec.model_validate(p)


def test_missing_link_fails_closed():
    assert "NO_EXISTING_REGISTRY_LINK" in validate_registry_link(
        spec(None), registry=MockRegistry()
    ).blockers


def test_unknown_link_fails_closed():
    assert "UNKNOWN_EXISTING_STRATEGY_ID" in validate_registry_link(
        spec("missing"), registry=MockRegistry()
    ).blockers


def test_existing_metadata_link_succeeds_without_authority():
    report = validate_registry_link(spec("existing"), registry=MockRegistry())
    assert report.linked and report.registry_payload["read_only"] is True


def test_invalid_registry_fails_closed():
    bad = SimpleNamespace(valid=False)
    assert "EXISTING_REGISTRY_INVALID" in validate_registry_link(
        spec("existing"), registry=bad
    ).blockers
