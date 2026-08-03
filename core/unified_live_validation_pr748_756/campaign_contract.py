"""Contracts for the PR #748-#756 unified live evidence campaign.

The campaign is evidence plumbing only. It must not subscribe to feeds, call a
broker, place orders, or grant live execution authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import os
import secrets
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Mapping


CAMPAIGN_SCHEMA_VERSION = 1
CAMPAIGN_NAME = "unified_live_validation_pr748_756_v1"
ENABLE_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE"
RUN_ID_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_RUN_ID"
EVIDENCE_ROOT_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_EVIDENCE_ROOT"
COMPOSITION_SHA_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_COMPOSITION_SHA"
SESSION_DATE_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_SESSION_DATE"
STATE_PATH_ENV = "MARKET_EVENT_GRAPH_LIVE_STATE_PATH"
IST = ZoneInfo("Asia/Kolkata")
READ_ONLY_FLAGS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
}
PR_HEADS = {
    748: "246e694ca9f4b5c0933659ddcecc6c363d4aa852",
    749: "f51119a67005b5efab185167055bb18681211ffc",
    750: "6d572b728b95ff8148d3c99b3a927e8d370fccd2",
    751: "410576ac2f0ee3c941b8bdebc0487fbd209439b9",
    752: "14507f7e93b08f1dadac3625f687454c18c41643",
    753: "881b70be448241bbef9a481805d27fe541adea14",
    754: "0a8d61048e06c9d48ff4ea14588d803200147e33",
    755: "5768cee9d104752c5070a46d47e57f4c22026172",
    756: "d51fbdcfee5330805d1b8d4893eca0898858a604",
}
DIRECT_LIVE_RUNTIME_PRS = frozenset({748, 749, 750, 756})
FORWARD_OBSERVATION_ONLY_PRS = frozenset({751, 752, 754, 755})
OFFLINE_ONLY_PRS = frozenset({753})


@dataclass(frozen=True)
class CampaignIdentity:
    run_id: str
    schema_version: int
    session_date: str
    campaign_commit_sha: str
    composition_manifest_sha: str
    evidence_root: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(READ_ONLY_FLAGS)
        return payload


def campaign_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(ENABLE_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def require_campaign_enabled(env: Mapping[str, str] | None = None) -> None:
    if not campaign_enabled(env):
        raise RuntimeError(f"{ENABLE_ENV}=true is required for campaign writes")


def current_commit_sha(cwd: Path | str = ".") -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def stable_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_session_date(explicit: str | None = None, env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    raw = str(explicit or source.get(SESSION_DATE_ENV) or datetime.now(IST).date().isoformat()).strip()
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("invalid_session_date:expected_YYYY-MM-DD") from exc
    return parsed.isoformat()


def build_composition_manifest(
    *,
    origin_main_sha: str,
    integrated_commit_sha: str,
    session_date: str | None = None,
    selected_constituent_producer: str = "pr_749_constituent_source_feeds_pr_748_validator_exporter",
) -> dict[str, Any]:
    manifest = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign": CAMPAIGN_NAME,
        "session_date": resolve_session_date(session_date),
        "origin_main_sha": origin_main_sha,
        "integrated_commit_sha": integrated_commit_sha,
        "activation_env": ENABLE_ENV,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "selected_live_constituent_producer": selected_constituent_producer,
        "live_runtime_prs": sorted(DIRECT_LIVE_RUNTIME_PRS),
        "forward_observation_only_prs": sorted(FORWARD_OBSERVATION_ONLY_PRS),
        "offline_only_prs": sorted(OFFLINE_ONLY_PRS),
        "pr_heads": {str(key): value for key, value in sorted(PR_HEADS.items())},
        "authority": {
            "748": "Market Event Graph launch plan, token union, observer registry, validator/exporter.",
            "749": "Authoritative live NIFTY constituent interval producer.",
            "750": "Feed truth, recovery states, execution-feed readiness, registry consistency.",
            "756": "Regime probability truth, feature quality, policy propagation, fail-closed scoring.",
        },
        "safety_constraints": [
            "no broker/order imports",
            "no websocket creation",
            "no runtime strategy registration",
            "no threshold or ranking mutation",
            "no production readiness or profitability certification",
        ],
    }
    manifest["composition_manifest_sha256"] = stable_json_sha256(manifest)
    return manifest


def build_campaign_identity(
    *,
    evidence_root: Path,
    campaign_commit_sha: str,
    composition_manifest_sha: str,
    nonce: str | None = None,
    live: bool = False,
    session_date: str | None = None,
) -> CampaignIdentity:
    suffix = nonce or secrets.token_hex(16)
    phase = "live" if live else "presession"
    canonical_session_date = resolve_session_date(session_date)
    raw_commit = str(campaign_commit_sha).strip()
    commit_component = raw_commit[:12] if len(raw_commit) >= 12 else composition_manifest_sha[:12]
    if not raw_commit:
        raise ValueError("campaign_commit_sha_required_for_run_identity")
    run_id = f"unified-pr748-756-{canonical_session_date.replace('-', '')}-{commit_component}-{phase}-{suffix}"
    return CampaignIdentity(
        run_id=run_id,
        schema_version=CAMPAIGN_SCHEMA_VERSION,
        session_date=canonical_session_date,
        campaign_commit_sha=campaign_commit_sha,
        composition_manifest_sha=composition_manifest_sha,
        evidence_root=str(evidence_root / run_id),
    )


def reject_presession_live_run_id(run_id: str) -> None:
    if "presession" in str(run_id):
        raise ValueError("presession_run_id_rejected_for_live_launch")


def require_fresh_evidence_root(identity: CampaignIdentity) -> Path:
    root = Path(identity.evidence_root)
    if root.exists():
        raise RuntimeError("RUN_ROOT_ALREADY_EXISTS")
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    return root


def enrich_row(identity: CampaignIdentity, row: Mapping[str, Any], *, pr_number: int) -> dict[str, Any]:
    if pr_number not in PR_HEADS:
        raise ValueError(f"unsupported_pr_number:{pr_number}")
    payload = {
        "run_id": identity.run_id,
        "campaign_schema_version": identity.schema_version,
        "session_date": identity.session_date,
        "campaign_commit_sha": identity.campaign_commit_sha,
        "originating_pr_number": pr_number,
        "originating_pr_head_sha": PR_HEADS[pr_number],
        "composition_manifest_sha": identity.composition_manifest_sha,
    }
    payload.update(READ_ONLY_FLAGS)
    payload.update(dict(row))
    payload.update(READ_ONLY_FLAGS)
    return payload
