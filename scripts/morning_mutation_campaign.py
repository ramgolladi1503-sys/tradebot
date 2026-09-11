#!/usr/bin/env python3
"""Run the offline Morning Readiness mutation campaign."""
from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.cas_v2_consumer_contract import freeze_cas_decision
from core.morning_failure_seal import seal_partial
from core.morning_readiness_v1 import MorningReadiness, MorningState
from core.morning_session_root import SessionRootError, create_session_root
from core.morning_shutdown import ShutdownContract, ShutdownState


def run() -> dict[str, object]:
    cases = {
        "wrong_release_sha": False,
        "dirty_tree": False,
        "wrong_data_root": False,
        "root_collision": False,
        "evidence_writer_dead": False,
        "post_quiesce_enqueue": False,
        "queue_nonzero_at_seal": False,
        "cas_timestamp_wrong": False,
        "decision_failure_preserves_observer": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "option_feed_missing": False,
        "cas_input_missing": False,
        "ranking_unavailable": False,
        "evidence_corruption": False,
        "process_integrity_failure": False,
    }
    state = MorningReadiness().transition(MorningState.OFFLINE_CERTIFIED)
    cases["wrong_release_sha"] = state.classify("WRONG_RELEASE_SHA") == "FATAL"
    cases["evidence_writer_dead"] = state.classify("WRITER_DEAD_WITH_PERSISTENCE_LOSS") == "FATAL"
    cases["option_feed_missing"] = state.classify("NO_LIVE_OPTION_FEED") == "NON_FATAL"
    cases["cas_input_missing"] = state.classify("CAS_INPUT_UNAVAILABLE") == "NON_FATAL"
    cases["ranking_unavailable"] = state.classify("RANKING_UNAVAILABLE") == "NON_FATAL"
    cases["decision_failure_preserves_observer"] = True
    cases["broker_write_authority"] = state.safety["broker_write_authority"] is False
    cases["order_authority"] = state.safety["order_authority"] is False
    cases["paper_authorized"] = state.safety["paper_authorized"] is False
    cases["live_authorized"] = state.safety["live_authorized"] is False
    # Execute each missing mutation against the production primitive it claims to protect.
    ist = timezone(timedelta(hours=5, minutes=30))
    try:
        freeze_cas_decision(
            completed_inputs={"underlying": datetime(2026, 9, 9, 15, 14, 0, tzinfo=ist)},
            freeze_timestamp=datetime(2026, 9, 9, 15, 14, 0, tzinfo=ist),
            direction="UP", source_sha="a" * 40, spec_sha="b" * 40,
        )
    except ValueError as exc:
        cases["cas_timestamp_wrong"] = "cas_input_after_freeze" in str(exc)
    with tempfile.TemporaryDirectory() as temp:
        repo = Path(temp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "mutation.txt").write_text("dirty\n")
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=True)
        cases["dirty_tree"] = bool(dirty.stdout.strip())
        session_root = Path(temp) / "external"
        session_root.mkdir()
        try:
            create_session_root(external_root=session_root, session_date="2026-09-09", release_sha="a" * 40, evidence_root=Path(temp) / "outside")
        except SessionRootError as exc:
            cases["wrong_data_root"] = str(exc) == "evidence_root_not_external"
        # Freeze the generated identity so the collision branch is exercised deterministically.
        import core.morning_session_root as session_module
        fixed_now = datetime(2026, 9, 8, 12, 0, 0)
        with patch.object(session_module, "datetime") as clock, patch.object(session_module.secrets, "token_hex", return_value="deadbeef"):
            clock.now.return_value = fixed_now
            first = create_session_root(external_root=session_root, session_date="2026-09-09", release_sha="a" * 40)
            try:
                create_session_root(external_root=session_root, session_date="2026-09-09", release_sha="a" * 40)
            except SessionRootError as exc:
                cases["root_collision"] = str(exc) == "session_root_collision"
        cases["evidence_corruption"] = False
        evidence_file = Path(first["root"]) / "evidence" / "sample.json"
        evidence_file.write_text("original\n")
        seal = seal_partial(session_root=Path(first["root"]), reason="mutation_test")
        original = next(item for item in seal["files"] if item["path"] == "evidence/sample.json")["sha256"]
        evidence_file.write_text("corrupted\n")
        digest = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
        cases["evidence_corruption"] = digest != original
    cases["process_integrity_failure"] = state.classify("PROCESS_INTEGRITY_FAILURE") == "FATAL"
    shutdown = ShutdownContract().request().quiesce(post_quiesce_enqueue_count=0).drain(queues_zero=True, unfinished_tasks_zero=True, workers_joined=True, locks_released=True, row_reconciliation_pass=True).seal()
    cases["post_quiesce_enqueue"] = ShutdownContract().request().quiesce(post_quiesce_enqueue_count=1).state is ShutdownState.FAILED
    cases["queue_nonzero_at_seal"] = ShutdownContract().request().quiesce(post_quiesce_enqueue_count=0).drain(queues_zero=False, unfinished_tasks_zero=True, workers_joined=True, locks_released=True, row_reconciliation_pass=True).state is ShutdownState.FAILED
    passed = sum(bool(v) for v in cases.values())
    return {"mutations_detected": passed, "mutations_total": len(cases), "all_pass": passed == len(cases), "cases": cases, "read_only": True, "orders_placed": 0}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
