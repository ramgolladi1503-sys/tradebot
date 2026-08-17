#!/usr/bin/env python3
"""Repository-level rehearsal for the 2026-08-18 governed observation program.

PASS here means the offline/preparation program is assembled and its exact-SHA
read-only/post-close contracts are present. It never means a live market tick
was observed, credentials are currently valid, disk is currently sufficient,
or any structural trading edge exists.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "tradebot-full-observation-program-readiness-v1"
OBSERVATION_DATE = "2026-08-18"
FROZEN_PRODUCER_SHA = "f0f5b3d3659415ab36662291e91b8f57fd8d1e07"
H1_SHA = "d8adee30f604cd8969a386afe3d74f6ace7016de"
PR815_SHA = "94bd5db86f9a2cadd16f0d349710df5c7194bb10"
T25_SHA = "1dfc08ca1a35f5e57c728201eb35bad3784479d5"
KERNEL_BASE_SHA = "46dd4f7df9b63486eb633a12baf25412cd4f761d"
KERNEL_INGESTION_SHA = "10d2f68b08026a269e9c25095bebca683ada67e5"
SUBSCRIPTION_SHA = "21f95a8b5908a8f6b9a0d7bbf459877efed41262"
POSTCLOSE_ORCHESTRATOR_SHA = "9ea3c1f38234ae6a5e6af30f734027ef43a79d89"
AIXION_SHA = "911ae2455a4fa6bfefedb11dc2d7f2ae82c20d2d"


class ReadinessError(ValueError):
    pass


def _git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
    if p.returncode != 0:
        raise ReadinessError(f"GIT_FAILED:{' '.join(args)}:{p.stderr.strip()}")
    return p.stdout


def _exact_sha(value: str, label: str) -> str:
    text = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", text):
        raise ReadinessError(f"{label}_EXACT_SHA_REQUIRED")
    return text


def _show(repo: Path, sha: str, path: str) -> str:
    _exact_sha(sha, "AUTHORITY")
    return _git(repo, "show", f"{sha}:{path}")


def _require(text: str, terms: list[str], label: str) -> None:
    missing = [term for term in terms if term not in text]
    if missing:
        raise ReadinessError(f"{label}_CONTRACT_MISSING:{missing}")


def validate(repo: Path) -> dict[str, Any]:
    root = repo.expanduser().resolve()
    if not (root / ".git").exists() and not _git(root, "rev-parse", "--is-inside-work-tree").strip() == "true":
        raise ReadinessError("REPO_REQUIRED")

    producer_launcher = _show(root, FROZEN_PRODUCER_SHA, "scripts/run_live_safe.sh")
    producer_gate = _show(root, FROZEN_PRODUCER_SHA, "core/pre_live_readiness_gate.py")
    cas = _show(root, FROZEN_PRODUCER_SHA, "scripts/run_cas_closing_auction_shadow_v1.py")
    _require(producer_launcher, ["python", "main.py"], "CORE_LAUNCHER")
    _require(producer_gate, ["PRE_LIVE_READINESS", "market_open"], "CORE_PREMARKET_GATE")
    _require(cas, ["15:15", "15:20", "15:30"], "CAS_WINDOWS")

    h1 = _show(root, H1_SHA, "scripts/research/hypothesis_factory/export_h1_live_capture_bars.py")
    _require(h1, ["256265", "09:15", "11:25", "no forward-fill"], "H1")

    pr815 = _show(root, PR815_SHA, "docs/research/prospective_market_evidence_pipeline_v1.md")
    _require(pr815, ["broker_write_authority=false", "live_authorized=false", "actual trusted live-runtime attestation producer remains a separate wiring requirement"], "PR815")

    t25 = _show(root, T25_SHA, "research/mros_certification/evaluation.py")
    _require(t25, ["sha256", "evidence_kind"], "T25")

    kernel_sealer = _show(root, KERNEL_INGESTION_SHA, "scripts/research/hypothesis_factory/seal_live_observation_bundle_v1.py")
    kernel_ingestor = _show(root, KERNEL_INGESTION_SHA, "scripts/research/hypothesis_factory/ingest_live_observation_evidence_v1.py")
    _require(kernel_sealer, [KERNEL_BASE_SHA, "PRESERVE_MISSING; NEVER_COERCE_TO_ZERO", '"live_authorized": False'], "KERNEL_SEALER")
    _require(kernel_ingestor, [KERNEL_BASE_SHA, "NON_PROSPECTIVE_SOURCE_REJECTED", "H1_27_BAR_CONTRACT_FAILED", "CAS_LIVE_PROMOTION_REJECTED"], "KERNEL_INGESTOR")

    subscription = _show(root, SUBSCRIPTION_SHA, "scripts/validate_subscription_reconciliation_postclose_v1.py")
    _require(subscription, ["PASS_POSTCLOSE_RECONCILIATION", "UNKNOWN_INCOMPLETE_SUBSCRIPTION_TRUTH", '"live_authorized": False'], "SUBSCRIPTION")

    orchestrator = _show(root, POSTCLOSE_ORCHESTRATOR_SHA, "scripts/research/run_postclose_observation_orchestrator_v1.py")
    _require(orchestrator, [FROZEN_PRODUCER_SHA, SUBSCRIPTION_SHA, KERNEL_INGESTION_SHA, '"live_authorized": False'], "POSTCLOSE_ORCHESTRATOR")

    aixion_observer = _show(root, AIXION_SHA, "scripts/run_tradebot_intelligence_observer.py")
    aixion_outcomes = _show(root, AIXION_SHA, "aixion_trade_intelligence/outcomes.py")
    _require(aixion_observer, ["--once", '"observer_mode": "READ_ONLY"', "--defer-finalization"], "AIXION_OBSERVER")
    _require(aixion_outcomes, ["option_entry_ask", "option_exit_bid", "OUTCOME_UNAVAILABLE"], "AIXION_OUTCOMES")

    advisory_path = root / "scripts" / "research" / "analyze_advisory_candidate_outcomes_postclose_v1.py"
    if not advisory_path.is_file():
        raise ReadinessError("ADVISORY_ANALYZER_MISSING")
    advisory = advisory_path.read_text(encoding="utf-8")
    _require(advisory, ["ts <= signal", '"counterfactual_only": True', '"realized_trade": False', '"realized_pnl": None', "AMBIGUOUS_SAME_TIMESTAMP", '"live_authorized": False'], "ADVISORY_ANALYTICS")

    lanes = {
        "CORE_PRODUCER_OPERATIONAL_READINESS": "PASS_REPOSITORY_PREP",
        "H1_OBSERVATION_LANE_READY": "PASS_PREP_ONLY",
        "PR815_OFFLINE": "PASS_READ_ONLY_COMPATIBILITY_ONLY",
        "MROS_T25_OFFLINE": "PASS",
        "KERNEL_INGESTION": "PASS_IMPLEMENTATION",
        "SUBSCRIPTION_RECONCILIATION": "PASS_OFFLINE",
        "AIXION": "PASS_POST_CLOSE_ONLY",
        "ADVISORY_ANALYTICS": "PASS_POST_CLOSE",
        "CAS": "PASS_LIMITED_CAPTURE_THEN_OFFLINE",
        "FULL_PROGRAM_INTEGRATION_REHEARSAL": "PASS_REPOSITORY_CONTRACTS",
    }
    return {
        "schema": SCHEMA,
        "observation_date": OBSERVATION_DATE,
        "authorities": {
            "producer": FROZEN_PRODUCER_SHA,
            "h1": H1_SHA,
            "pr815": PR815_SHA,
            "t25": T25_SHA,
            "kernel_base": KERNEL_BASE_SHA,
            "kernel_ingestion": KERNEL_INGESTION_SHA,
            "subscription": SUBSCRIPTION_SHA,
            "postclose_orchestrator": POSTCLOSE_ORCHESTRATOR_SHA,
            "aixion": AIXION_SHA,
        },
        "lanes": lanes,
        "FULL_OBSERVATION_PROGRAM_READY": "PASS",
        "PASS_SCOPE": "PREMARKET_REPOSITORY_AND_POSTCLOSE_PROGRAM_READINESS_ONLY",
        "required_operator_preflight": [
            "producer worktree exact SHA and clean",
            "internal disk >=10 GiB",
            "credentials/auth healthy",
            "no stale or competing producer/feed process",
            "all runtime authority flags false",
            "H1 runtime root writable and producer SQLite readable",
        ],
        "required_after_market_open": ["actual advancing live tick proof from frozen producer evidence"],
        "LIVE_READY": False,
        "LIVE_VERIFIED": False,
        "PROSPECTIVE_SUPPORTED": False,
        "STRUCTURAL_EDGE_CERTIFIED": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "no_market_hours_secondary_observer": True,
        "aixion_market_hours_attach_allowed": False,
        "pr815_live_attestation_producer_implemented": False,
    }


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    target = path.expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ReadinessError("OUTPUT_ALREADY_EXISTS") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = validate(args.repo)
    if args.output:
        _write_once(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
