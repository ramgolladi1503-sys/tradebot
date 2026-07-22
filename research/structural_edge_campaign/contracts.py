from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CampaignContractError(ValueError):
    """Raised when a structural-edge campaign contract is invalid."""


@dataclass(frozen=True)
class CampaignThresholds:
    min_option_trades: int
    min_after_cost_expectancy: float
    min_profit_factor: float
    max_drawdown: float
    min_positive_wfa_partition_fraction: float
    expectancy_basis: str
    drawdown_basis: str
    max_contamination_count: int = 0
    max_ambiguity_count: int = 0
    max_fallback_rows: int = 0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "CampaignThresholds":
        required = {
            "min_option_trades",
            "min_after_cost_expectancy",
            "min_profit_factor",
            "max_drawdown",
            "min_positive_wfa_partition_fraction",
            "expectancy_basis",
            "drawdown_basis",
        }
        missing = sorted(required - set(raw))
        if missing:
            raise CampaignContractError(
                f"campaign thresholds missing required fields: {missing}"
            )
        instance = cls(
            min_option_trades=int(raw["min_option_trades"]),
            min_after_cost_expectancy=float(raw["min_after_cost_expectancy"]),
            min_profit_factor=float(raw["min_profit_factor"]),
            max_drawdown=float(raw["max_drawdown"]),
            min_positive_wfa_partition_fraction=float(
                raw["min_positive_wfa_partition_fraction"]
            ),
            expectancy_basis=str(raw["expectancy_basis"]).strip(),
            drawdown_basis=str(raw["drawdown_basis"]).strip(),
            max_contamination_count=int(raw.get("max_contamination_count", 0)),
            max_ambiguity_count=int(raw.get("max_ambiguity_count", 0)),
            max_fallback_rows=int(raw.get("max_fallback_rows", 0)),
        )
        if instance.min_option_trades <= 0:
            raise CampaignContractError("min_option_trades must be positive")
        if instance.min_profit_factor <= 1.0:
            raise CampaignContractError(
                "min_profit_factor must exceed 1.0 for structural-edge screening"
            )
        if instance.max_drawdown < 0.0:
            raise CampaignContractError("max_drawdown must be nonnegative")
        if not instance.expectancy_basis:
            raise CampaignContractError("expectancy_basis is required")
        if not instance.drawdown_basis:
            raise CampaignContractError("drawdown_basis is required")
        if not 0.0 <= instance.min_positive_wfa_partition_fraction <= 1.0:
            raise CampaignContractError(
                "min_positive_wfa_partition_fraction must be in [0, 1]"
            )
        for name in (
            "max_contamination_count",
            "max_ambiguity_count",
            "max_fallback_rows",
        ):
            if getattr(instance, name) < 0:
                raise CampaignContractError(f"{name} must be nonnegative")
        return instance


@dataclass(frozen=True)
class HypothesisContract:
    hypothesis_id: str
    family: str
    frozen_spec_sha256: str
    spec_path: str
    evidence_dir: str
    max_variants: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "HypothesisContract":
        hypothesis_id = str(raw.get("hypothesis_id", "")).strip()
        family = str(raw.get("family", "")).strip()
        frozen_spec_sha256 = str(raw.get("frozen_spec_sha256", "")).strip().lower()
        spec_path = str(raw.get("spec_path", "")).strip()
        evidence_dir = str(raw.get("evidence_dir", "")).strip()
        max_variants = int(raw.get("max_variants", 0))
        if not hypothesis_id:
            raise CampaignContractError("hypothesis_id is required")
        if not family:
            raise CampaignContractError(f"{hypothesis_id}: family is required")
        if not _SHA256_RE.fullmatch(frozen_spec_sha256):
            raise CampaignContractError(
                f"{hypothesis_id}: frozen_spec_sha256 must be a lowercase SHA-256"
            )
        for field_name, value in (("spec_path", spec_path), ("evidence_dir", evidence_dir)):
            path = Path(value)
            if not value or path.is_absolute() or ".." in path.parts:
                raise CampaignContractError(
                    f"{hypothesis_id}: {field_name} must be a safe non-empty relative path"
                )
        if max_variants <= 0:
            raise CampaignContractError(
                f"{hypothesis_id}: max_variants must be positive"
            )
        return cls(
            hypothesis_id=hypothesis_id,
            family=family,
            frozen_spec_sha256=frozen_spec_sha256,
            spec_path=spec_path,
            evidence_dir=evidence_dir,
            max_variants=max_variants,
        )


@dataclass(frozen=True)
class CampaignContract:
    schema_version: str
    campaign_id: str
    global_holdout_id: str
    max_total_hypotheses: int
    hypotheses: tuple[HypothesisContract, ...]
    thresholds: CampaignThresholds

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "CampaignContract":
        schema_version = str(raw.get("schema_version", "")).strip()
        campaign_id = str(raw.get("campaign_id", "")).strip()
        global_holdout_id = str(raw.get("global_holdout_id", "")).strip()
        max_total_hypotheses = int(raw.get("max_total_hypotheses", 0))
        raw_hypotheses = raw.get("hypotheses")
        if schema_version != "1.0":
            raise CampaignContractError("unsupported campaign schema_version")
        if not campaign_id:
            raise CampaignContractError("campaign_id is required")
        if not global_holdout_id:
            raise CampaignContractError("global_holdout_id is required")
        if max_total_hypotheses <= 0:
            raise CampaignContractError("max_total_hypotheses must be positive")
        if not isinstance(raw_hypotheses, list) or not raw_hypotheses:
            raise CampaignContractError("hypotheses must be a non-empty list")
        hypotheses = tuple(
            HypothesisContract.from_mapping(item) for item in raw_hypotheses
        )
        ids = [item.hypothesis_id for item in hypotheses]
        if len(ids) != len(set(ids)):
            raise CampaignContractError("hypothesis_id values must be unique")
        dirs = [item.evidence_dir for item in hypotheses]
        if len(dirs) != len(set(dirs)):
            raise CampaignContractError("evidence_dir values must be unique")
        paths = [item.spec_path for item in hypotheses]
        if len(paths) != len(set(paths)):
            raise CampaignContractError("spec_path values must be unique")
        if len(hypotheses) > max_total_hypotheses:
            raise CampaignContractError(
                "hypothesis registry exceeds max_total_hypotheses"
            )
        total_variants = sum(item.max_variants for item in hypotheses)
        if total_variants > 40:
            raise CampaignContractError(
                "campaign search budget exceeds the frozen 40-variant ceiling"
            )
        thresholds = CampaignThresholds.from_mapping(
            raw.get("thresholds") if isinstance(raw.get("thresholds"), Mapping) else {}
        )
        return cls(
            schema_version=schema_version,
            campaign_id=campaign_id,
            global_holdout_id=global_holdout_id,
            max_total_hypotheses=max_total_hypotheses,
            hypotheses=hypotheses,
            thresholds=thresholds,
        )

    @classmethod
    def load(cls, path: str | Path) -> "CampaignContract":
        contract_path = Path(path).expanduser().resolve()
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise CampaignContractError("campaign contract must contain a JSON object")
        contract = cls.from_mapping(payload)
        root = contract_path.parent
        for hypothesis in contract.hypotheses:
            spec_path = (root / hypothesis.spec_path).resolve()
            if root != spec_path and root not in spec_path.parents:
                raise CampaignContractError(
                    f"{hypothesis.hypothesis_id}: spec path escapes campaign root"
                )
            if not spec_path.is_file():
                raise CampaignContractError(
                    f"{hypothesis.hypothesis_id}: frozen spec is missing: {spec_path}"
                )
            digest = hashlib.sha256(spec_path.read_bytes()).hexdigest()
            if digest != hypothesis.frozen_spec_sha256:
                raise CampaignContractError(
                    f"{hypothesis.hypothesis_id}: frozen spec SHA-256 mismatch"
                )
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            if not isinstance(spec, Mapping):
                raise CampaignContractError(
                    f"{hypothesis.hypothesis_id}: frozen spec must be a JSON object"
                )
            expected = {
                "hypothesis_id": hypothesis.hypothesis_id,
                "family": hypothesis.family,
                "max_variants": hypothesis.max_variants,
            }
            for field, value in expected.items():
                if spec.get(field) != value:
                    raise CampaignContractError(
                        f"{hypothesis.hypothesis_id}: spec {field} mismatch"
                    )
        return contract
