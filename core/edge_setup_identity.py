from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

EDGE_SETUP_IDENTITY_SCHEMA_VERSION = 1

_SCORE_BUCKETS = (
    (0.0, 0.25, "0.00-0.25"),
    (0.25, 0.50, "0.25-0.50"),
    (0.50, 0.75, "0.50-0.75"),
    (0.75, 1.0000001, "0.75-1.00"),
)
_ALLOWED_SCORE_BUCKETS = frozenset(label for _, _, label in _SCORE_BUCKETS)


class EdgeSetupIdentityError(ValueError):
    pass


@dataclass(frozen=True)
class EdgeSetupIdentity:
    schema_version: int
    candidate_id: str
    setup_id: str
    strategy_family: str
    regime_key: str
    entry_rule_id: str
    exit_rule_id: str
    cost_model_version: str
    score_bucket: str
    final_score: float | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise EdgeSetupIdentityError("edge_setup_mapping_required")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _code(value: Any, field: str) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    if not text:
        raise EdgeSetupIdentityError(f"edge_setup_field_blank:{field}")
    return text


def _slug(value: Any, field: str) -> str:
    text = _text(value).lower().replace("_", "-").replace(" ", "-")
    if not text:
        raise EdgeSetupIdentityError(f"edge_setup_field_blank:{field}")
    return text


def _score(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        number = float(value)
    except Exception:
        return None
    if number != number:
        return None
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    if number < 0.0 or number > 1.0:
        raise EdgeSetupIdentityError("edge_setup_score_out_of_range")
    return number


def score_bucket_for_score(score: float) -> str:
    normalized = _score(score)
    if normalized is None:
        raise EdgeSetupIdentityError("edge_setup_score_required")
    for lower, upper, label in _SCORE_BUCKETS:
        if lower <= normalized < upper:
            return label
    raise EdgeSetupIdentityError("edge_setup_score_bucket_unmapped")


def _score_bucket(row: Mapping[str, Any], final_score: float | None) -> str:
    explicit = _text(row.get("score_bucket"))
    if explicit:
        if explicit not in _ALLOWED_SCORE_BUCKETS:
            raise EdgeSetupIdentityError(f"edge_setup_score_bucket_invalid:{explicit}")
        return explicit
    if final_score is None:
        raise EdgeSetupIdentityError("edge_setup_score_bucket_required")
    return score_bucket_for_score(final_score)


def build_edge_setup_identity(record: Any) -> EdgeSetupIdentity:
    row = _mapping(record)
    final_score = _score(row.get("final_score") if row.get("final_score") is not None else row.get("score"))
    return EdgeSetupIdentity(
        schema_version=EDGE_SETUP_IDENTITY_SCHEMA_VERSION,
        candidate_id=_code(row.get("candidate_id") or row.get("trade_id"), "candidate_id"),
        setup_id=_code(row.get("setup_id"), "setup_id"),
        strategy_family=_slug(row.get("strategy_family") or row.get("family") or row.get("strategy"), "strategy_family"),
        regime_key=_code(row.get("regime_key") or row.get("regime"), "regime_key"),
        entry_rule_id=_code(row.get("entry_rule_id"), "entry_rule_id"),
        exit_rule_id=_code(row.get("exit_rule_id"), "exit_rule_id"),
        cost_model_version=_code(row.get("cost_model_version"), "cost_model_version"),
        score_bucket=_score_bucket(row, final_score),
        final_score=final_score,
        source="edge_setup_identity_contract",
    )


def enrich_record_with_edge_setup_identity(record: Any) -> dict[str, Any]:
    row = dict(_mapping(record))
    identity = build_edge_setup_identity(row).to_dict()
    enriched = dict(row)
    for key, value in identity.items():
        if key in {"schema_version", "source"}:
            continue
        enriched[key] = value
    metadata = dict(enriched.get("metadata") or {})
    metadata["edge_setup_identity"] = identity
    enriched["metadata"] = metadata
    return enriched
