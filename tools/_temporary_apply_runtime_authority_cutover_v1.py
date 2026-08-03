from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True)


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"PATCH_CONTEXT_MISSING:{path}:{old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, content: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if marker in text:
        return
    target.write_text(text.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")


def copy_from(ref: str, path: str) -> None:
    write(path, run("git", "show", f"{ref}:{path}"))


subprocess.run(
    ["git", "fetch", "origin", "agent/runtime-authority-hardening-v1", "hardening/trade-builder-orchestration-v1"],
    cwd=ROOT,
    check=True,
)

# Preserve the stronger PR #757 authority model and its focused proofs.
for source_path in (
    "core/canonical_execution_decision.py",
    "core/runtime_authority_contract.py",
    "core/ranking_authority.py",
    "tests/test_canonical_execution_decision.py",
    "tests/test_runtime_authority_contract.py",
    "tests/test_ranking_authority.py",
):
    copy_from("origin/agent/runtime-authority-hardening-v1", source_path)

write(
    "core/runtime_authority_cutover.py",
    r'''"""Authoritative execution-selection and operator-view cutover.

This module converts fragmented candidate fields into one immutable authority
answer.  It is feed-agnostic: it reads existing quote/feed evidence but never
subscribes, reconnects, places orders, or mutates MEG state.
"""
from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass, replace
from typing import Any, Iterable, Mapping

from config import config as cfg
from core.canonical_execution_decision import ExecutionState, derive_canonical_execution_decision
from core.live_fallback_execution_contract import (
    enforce_live_fallback_execution_contract,
    is_fallback_execution_candidate,
)

AUTHORITY_SCHEMA_VERSION = 1
_AUTHORITY_EVIDENCE_FIELDS = {
    "authority_state",
    "authority_allowed",
    "canonical_execution_decision",
    "execution_allowed",
    "eligible_for_execution",
    "execution_entry_status",
    "execution_blocked",
    "permission",
    "final_action",
}


def _get(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _mapping(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, Mapping):
        return dict(candidate)
    if is_dataclass(candidate):
        return {item.name: getattr(candidate, item.name) for item in fields(candidate)}
    try:
        return dict(vars(candidate))
    except Exception:
        return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return float(default)
    return float(default) if number != number else number


def _mode(mode: str | None) -> str:
    return str(mode or getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper()


def _diagnostic_score(row: Mapping[str, Any]) -> float:
    for field in (
        "diagnostic_score",
        "opportunity_score",
        "final_score",
        "priority_score",
        "rank_score",
        "confidence_final",
        "confidence",
        "confidence_raw",
    ):
        value = row.get(field)
        if value not in (None, "", "None"):
            return max(0.0, _safe_float(value))
    return 0.0


def _selection_score(row: Mapping[str, Any]) -> float:
    for field in (
        "selection_score",
        "priority_score",
        "final_score",
        "opportunity_score",
        "execution_score",
        "rank_score",
        "confidence_final",
        "confidence",
    ):
        value = row.get(field)
        if value not in (None, "", "None"):
            return max(0.0, _safe_float(value))
    return 0.0


def has_runtime_authority_evidence(candidate: Any) -> bool:
    row = _mapping(candidate)
    return any(field in row for field in _AUTHORITY_EVIDENCE_FIELDS)


def _operator_bucket(row: Mapping[str, Any], state: ExecutionState) -> str:
    if state is ExecutionState.EXECUTABLE:
        return "TOP_EXECUTABLE"
    # Fallback rows remain visible as advisory evidence, never as executable.
    if is_fallback_execution_candidate(row):
        return "ADVISORY_ONLY"
    if state is ExecutionState.ADVISORY_ONLY:
        return "ADVISORY_ONLY"
    return "BLOCKED_DEBUG"


def authority_payload(candidate: Any, *, mode: str | None = None) -> dict[str, Any]:
    runtime_mode = _mode(mode)
    row = _mapping(candidate)
    if runtime_mode in {"LIVE", "REAL"}:
        row = enforce_live_fallback_execution_contract(row, runtime_mode)
    decision = derive_canonical_execution_decision(row)
    diagnostic = _diagnostic_score(row)
    opportunity = max(0.0, _safe_float(row.get("opportunity_score"), diagnostic))
    selection = _selection_score(row) if decision.allowed else 0.0
    bucket = _operator_bucket(row, decision.state)
    return {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "mode": runtime_mode,
        "state": decision.state.value,
        "allowed": bool(decision.allowed),
        "primary_reason": decision.primary_reason,
        "blockers": list(decision.blockers),
        "contradictions": list(decision.contradictions),
        "operator_bucket": bucket,
        "diagnostic_score": diagnostic,
        "opportunity_score": opportunity,
        "selection_score": selection,
        "decision": decision.to_payload(),
        "is_order_action": False,
    }


def _updates(candidate: Any, *, mode: str | None = None) -> dict[str, Any]:
    row = _mapping(candidate)
    payload = authority_payload(row, mode=mode)
    allowed = bool(payload["allowed"])
    state = str(payload["state"])
    bucket = str(payload["operator_bucket"])
    updates: dict[str, Any] = {
        "authority_schema_version": AUTHORITY_SCHEMA_VERSION,
        "authority_state": state,
        "authority_allowed": allowed,
        "authority_reason": payload["primary_reason"],
        "authority_blockers": list(payload["blockers"]),
        "operator_bucket": bucket,
        "canonical_execution_decision": dict(payload["decision"]),
        "diagnostic_score": float(payload["diagnostic_score"]),
        "opportunity_score": float(payload["opportunity_score"]),
        "selection_score": float(payload["selection_score"]),
    }
    if not allowed:
        updates.update(
            {
                "execution_allowed": False,
                "eligible_for_execution": False,
                "truth_allows_execution": False,
                "tradable": False,
                "execution_ok": False,
                "execution_blocked": True,
                "selected_for_execution": False,
                "portfolio_optimization_selected": False,
                "capital_assigned": 0.0,
                "allocated_capital": 0.0,
                "position_size_estimate": 0.0,
                "slot_id": None,
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "max_final_action": "QUEUE_ONLY",
                "execution_status": "not_executable",
                "candidate_status": "advisory" if bucket == "ADVISORY_ONLY" else "blocked",
            }
        )
    return updates


def apply_runtime_authority(candidate: Any, *, mode: str | None = None) -> Any:
    """Return a same-shape candidate stamped with authoritative execution truth."""
    updates = _updates(candidate, mode=mode)
    if isinstance(candidate, Mapping):
        out = dict(candidate)
        out.update(updates)
        return out
    if is_dataclass(candidate):
        valid = {item.name for item in fields(candidate)}
        applicable = {key: value for key, value in updates.items() if key in valid}
        out = replace(candidate, **applicable)
        # Non-field authority evidence is attached only when the object permits it.
        for key, value in updates.items():
            if key in applicable:
                continue
            try:
                object.__setattr__(out, key, value)
            except Exception:
                pass
        return out
    try:
        out = copy.copy(candidate)
    except Exception:
        out = candidate
    for key, value in updates.items():
        try:
            setattr(out, key, value)
        except Exception:
            pass
    return out


def authority_allows_execution(candidate: Any) -> bool:
    return bool(_get(candidate, "authority_allowed", False)) and str(
        _get(candidate, "authority_state", "")
    ).upper() == ExecutionState.EXECUTABLE.value


def normalize_selection_result(result: Any, *, mode: str | None = None) -> Any:
    if result is None:
        return None
    if isinstance(result, tuple):
        return tuple(normalize_selection_result(item, mode=mode) for item in result)
    if isinstance(result, list):
        return [apply_runtime_authority(item, mode=mode) for item in result]
    if isinstance(result, Mapping) or hasattr(result, "__dict__"):
        return apply_runtime_authority(result, mode=mode)
    return result


def partition_operator_candidates(
    candidates: Iterable[Any], *, mode: str | None = None
) -> dict[str, list[Any]]:
    stamped = [apply_runtime_authority(candidate, mode=mode) for candidate in candidates]
    executable = [row for row in stamped if authority_allows_execution(row)]
    advisory = [row for row in stamped if _get(row, "operator_bucket") == "ADVISORY_ONLY"]
    blocked = [row for row in stamped if _get(row, "operator_bucket") == "BLOCKED_DEBUG"]
    executable.sort(key=lambda row: _safe_float(_get(row, "selection_score")), reverse=True)
    advisory.sort(key=lambda row: _safe_float(_get(row, "diagnostic_score")), reverse=True)
    blocked.sort(key=lambda row: _safe_float(_get(row, "diagnostic_score")), reverse=True)
    return {
        "top_executable": executable,
        "advisory": advisory,
        "blocked_debug": blocked,
        "all_candidates": stamped,
    }


def preflight_execution_authority(candidate: Any, *, mode: str | None = None) -> dict[str, Any] | None:
    """Final router firewall for candidates emitted by the authority-cutover path.

    Legacy tests/tools that do not yet carry authority evidence retain their old
    behavior. Every candidate emitted by the cutover is stamped, so runtime
    selection cannot bypass this firewall.
    """
    if not has_runtime_authority_evidence(candidate):
        return None
    payload = authority_payload(candidate, mode=mode)
    return {
        "allowed": bool(payload["allowed"]),
        "state": payload["state"],
        "reason": payload["primary_reason"],
        "blockers": list(payload["blockers"]),
        "selection_score": float(payload["selection_score"]),
        "operator_bucket": payload["operator_bucket"],
    }


__all__ = [
    "AUTHORITY_SCHEMA_VERSION",
    "apply_runtime_authority",
    "authority_allows_execution",
    "authority_payload",
    "has_runtime_authority_evidence",
    "normalize_selection_result",
    "partition_operator_candidates",
    "preflight_execution_authority",
]
''',
)

append_once(
    "core/opportunity_engine.py",
    "_RUNTIME_AUTHORITY_CUTOVER_WRAPPER_V1",
    r'''
# _RUNTIME_AUTHORITY_CUTOVER_WRAPPER_V1
# The legacy scorer remains intact; authoritative eligibility is now applied
# before it can select or allocate capital, and the returned result is checked
# again before leaving this module.
_RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY = select_best_opportunity


def select_best_opportunity(candidates, *args, **kwargs):  # noqa: F811
    from core.runtime_authority_cutover import (
        apply_runtime_authority,
        authority_allows_execution,
        normalize_selection_result,
    )

    mode = str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").upper()
    stamped = [apply_runtime_authority(candidate, mode=mode) for candidate in list(candidates or [])]
    executable = [candidate for candidate in stamped if authority_allows_execution(candidate)]
    result = _RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY(
        executable,
        *args,
        **kwargs,
    )
    return normalize_selection_result(result, mode=mode)


select_best_opportunity._runtime_authority_cutover = True
''',
)

replace_once(
    "core/execution_router.py",
    "from core.feed.gate import check_execution_allowed\n",
    "from core.feed.gate import check_execution_allowed\nfrom core.runtime_authority_cutover import preflight_execution_authority\n",
)
replace_once(
    "core/execution_router.py",
    "        mode = str(getattr(cfg, \"EXECUTION_MODE\", \"SIM\")).upper()\n        try:\n            execution_plan = ExecutionPlan.from_trade(trade, mode=mode)\n",
    "        mode = str(getattr(cfg, \"EXECUTION_MODE\", \"SIM\")).upper()\n        authority = preflight_execution_authority(trade, mode=mode)\n        if authority is not None and not bool(authority.get(\"allowed\")):\n            return False, None, {\n                \"decision_mid\": None,\n                \"decision_spread\": None,\n                \"fill_price\": None,\n                \"slippage\": None,\n                \"reason_if_aborted\": f\"runtime_authority_blocked:{authority.get('reason')}\",\n                \"runtime_authority\": authority,\n            }\n        try:\n            execution_plan = ExecutionPlan.from_trade(trade, mode=mode)\n",
)

replace_once(
    "core/runtime_snapshot_producer.py",
    "from core.runtime_snapshot_stages import (\n",
    "from core.runtime_authority_cutover import apply_runtime_authority, authority_allows_execution\nfrom core.runtime_snapshot_stages import (\n",
)
replace_once(
    "core/runtime_snapshot_producer.py",
    "    return serialize_advisory_row(advisory_payload, allow_legacy=True)\n\n\ndef _build_and_write_canonical_ranked_snapshot(\n",
    "    advisory_payload = apply_runtime_authority(\n        advisory_payload,\n        mode=str(getattr(cfg, 'EXECUTION_MODE', 'SIM') or 'SIM'),\n    )\n    return serialize_advisory_row(advisory_payload, allow_legacy=True)\n\n\ndef _build_and_write_canonical_ranked_snapshot(\n",
)
replace_once(
    "core/runtime_snapshot_producer.py",
    "                row = adapt_candidate_rank_record_to_ui(rank_dict)\n\n                # Check for fake entry prices (Point 3)\n",
    "                row = adapt_candidate_rank_record_to_ui(rank_dict)\n                row = apply_runtime_authority(\n                    row,\n                    mode=str(getattr(cfg, 'EXECUTION_MODE', 'SIM') or 'SIM'),\n                )\n\n                # Check for fake entry prices (Point 3)\n",
)
replace_once(
    "core/runtime_snapshot_producer.py",
    "                if rank.bucket == \"EXECUTABLE_CANDIDATE\" and has_entry:\n",
    "                if authority_allows_execution(row) and has_entry:\n",
)

replace_once(
    "dashboard/ui/table_model.py",
    "from core.top_opportunity_executable_truth import classify_top_opportunity_row\n",
    "from core.top_opportunity_executable_truth import classify_top_opportunity_row\nfrom core.runtime_authority_cutover import apply_runtime_authority\n",
)
replace_once(
    "dashboard/ui/table_model.py",
    "ui_execution_truth ui_execution_truth_reason top_opportunity_truth_reason hard_blockers soft_penalties warnings trade_key tradingsymbol\n",
    "ui_execution_truth ui_execution_truth_reason top_opportunity_truth_reason authority_state authority_allowed authority_reason authority_blockers operator_bucket diagnostic_score opportunity_score selection_score selected_for_execution capital_assigned hard_blockers soft_penalties warnings trade_key tradingsymbol\n",
)
replace_once(
    "dashboard/ui/table_model.py",
    "def normalize_df(df: pd.DataFrame | None) -> pd.DataFrame:\n",
    r'''def _stamp_runtime_authority(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty:
        return out
    mode = str(getattr(__import__("config.config", fromlist=["EXECUTION_MODE"]), "EXECUTION_MODE", "SIM") or "SIM")
    rows = [apply_runtime_authority(row, mode=mode) for row in out.to_dict(orient="records")]
    stamped = pd.DataFrame(rows, index=out.index)
    # Preserve all original columns and expose authority fields as additional
    # operator truth. Non-executable rows retain diagnostic/opportunity scores,
    # but selection_score and capital are forced to zero by the authority layer.
    for column in out.columns:
        if column not in stamped.columns:
            stamped[column] = out[column]
    return stamped


def normalize_df(df: pd.DataFrame | None) -> pd.DataFrame:
''',
)
replace_once(
    "dashboard/ui/table_model.py",
    "    return _stamp_ui_execution_truth(out)\n",
    "    return _stamp_runtime_authority(_stamp_ui_execution_truth(out))\n",
)

write(
    "tests/test_runtime_authority_cutover_v1.py",
    r'''from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from config import config as cfg
from core.runtime_authority_cutover import (
    apply_runtime_authority,
    authority_allows_execution,
    partition_operator_candidates,
)


def _executable(candidate_id: str, score: float) -> dict:
    return {
        "trade_id": candidate_id,
        "symbol": "NIFTY",
        "quote_source": "LIVE",
        "best_bid": 100.0,
        "best_ask": 101.0,
        "quote_age_sec": 0.1,
        "execution_allowed": True,
        "eligible_for_execution": True,
        "tradable": True,
        "execution_ok": True,
        "execution_entry": 101.0,
        "execution_entry_status": "EXECUTABLE",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "candidate_status": "READY",
        "selection_score": score,
        "opportunity_score": score,
    }


def test_recovered_fallback_is_visible_advisory_never_executable_or_allocated():
    row = _executable("fallback", 0.99)
    row.update({"recovered_fallback": True, "capital_assigned": 10000.0})
    stamped = apply_runtime_authority(row, mode="LIVE")
    assert stamped["operator_bucket"] == "ADVISORY_ONLY"
    assert stamped["authority_allowed"] is False
    assert stamped["selection_score"] == 0.0
    assert stamped["capital_assigned"] == 0.0
    assert stamped["selected_for_execution"] is False
    assert stamped["permission"] == "QUEUE_ONLY"


def test_unknown_or_stale_quote_cannot_become_executable():
    unknown = _executable("unknown", 0.8)
    unknown["quote_source"] = ""
    stale = _executable("stale", 0.7)
    stale["fresh_quote_ok"] = False
    for row in (unknown, stale):
        stamped = apply_runtime_authority(row, mode="LIVE")
        assert stamped["authority_allowed"] is False
        assert stamped["selection_score"] == 0.0
        assert not authority_allows_execution(stamped)


def test_operator_partition_ranks_only_executable_by_selection_score():
    strong = _executable("strong", 0.82)
    weak = _executable("weak", 0.51)
    advisory = _executable("advisory", 0.97)
    advisory["recovered_fallback"] = True
    partition = partition_operator_candidates([weak, advisory, strong], mode="LIVE")
    assert [row["trade_id"] for row in partition["top_executable"]] == ["strong", "weak"]
    assert [row["trade_id"] for row in partition["advisory"]] == ["advisory"]
    assert partition["advisory"][0]["selection_score"] == 0.0


def test_actual_opportunity_selector_never_receives_advisory(monkeypatch):
    import core.opportunity_engine as engine

    captured = {}

    def fake_legacy(candidates, *args, **kwargs):
        captured["ids"] = [getattr(row, "trade_id", row.get("trade_id")) for row in candidates]
        return candidates[0] if candidates else None

    monkeypatch.setattr(engine, "_RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY", fake_legacy)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    advisory = _executable("advisory", 0.99)
    advisory["recovered_fallback"] = True
    result = engine.select_best_opportunity(
        [advisory, _executable("valid", 0.62)],
        scope="unit",
    )
    assert captured["ids"] == ["valid"]
    assert getattr(result, "trade_id", result.get("trade_id")) == "valid"


def test_execution_router_authority_firewall_runs_before_order_or_approval():
    from core.execution_router import ExecutionRouter

    trade = SimpleNamespace(**apply_runtime_authority({
        **_executable("blocked-router", 0.9),
        "recovered_fallback": True,
    }, mode="LIVE"))
    router = object.__new__(ExecutionRouter)
    filled, price, report = router.execute(
        trade,
        bid=100.0,
        ask=101.0,
        volume=1000,
    )
    assert filled is False
    assert price is None
    assert report["reason_if_aborted"].startswith("runtime_authority_blocked:")
    assert report["runtime_authority"]["allowed"] is False


def test_dashboard_model_separates_operator_truth_and_zeroes_selection_score(monkeypatch):
    from dashboard.ui.table_model import normalize_df

    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    frame = pd.DataFrame([
        {
            **_executable("ui-valid", 0.73),
            "timestamp": "2026-08-03T10:00:00+05:30",
            "instrument_type": "OPT",
            "option_type": "CE",
            "strike": 25000,
            "expiry_date": "2026-08-04",
            "side": "BUY",
            "status": "READY",
        },
        {
            **_executable("ui-advisory", 0.95),
            "recovered_fallback": True,
            "timestamp": "2026-08-03T10:00:00+05:30",
            "instrument_type": "OPT",
            "option_type": "CE",
            "strike": 25100,
            "expiry_date": "2026-08-04",
            "side": "BUY",
            "status": "ADVISORY_ONLY",
        },
    ])
    out = normalize_df(frame)
    valid = out.loc[out["trade_id"] == "ui-valid"].iloc[0]
    advisory = out.loc[out["trade_id"] == "ui-advisory"].iloc[0]
    assert valid["operator_bucket"] == "TOP_EXECUTABLE"
    assert float(valid["selection_score"]) == 0.73
    assert advisory["operator_bucket"] == "ADVISORY_ONLY"
    assert float(advisory["selection_score"]) == 0.0
''',
)

write(
    "docs/architecture/runtime_authority_cutover_v1.md",
    r'''# Runtime Authority Cutover V1

## Scope

This stacked post-PR763 change promotes one canonical execution authority into the actual candidate-selection, runtime-snapshot, operator-UI, and execution-router paths.

It does not modify market data, WebSocket subscriptions, feed recovery, persistence workers, Market Event Graph code, strategy formulas, ranking weights, risk thresholds, broker clients, or order placement.

## Authoritative flow

```text
candidate evidence
→ canonical executable truth
→ EXECUTABLE / ADVISORY_ONLY / BLOCKED
→ selection_score and capital firewall
→ legacy scorer receives EXECUTABLE candidates only
→ runtime snapshot and UI expose separate buckets
→ ExecutionRouter verifies authority again before approval/simulation
```

## Invariants

- fallback, recovered fallback, synthetic, unknown, stale, missing-spread, or contradictory candidates cannot execute;
- non-executable candidates retain diagnostic and opportunity scores;
- non-executable LIVE `selection_score` is zero;
- non-executable candidates receive zero capital and no portfolio slot;
- operator output separates `TOP_EXECUTABLE`, `ADVISORY_ONLY`, and `BLOCKED_DEBUG`;
- high confidence cannot override executable truth;
- the execution router rejects stamped non-executable candidates before approval or fill simulation;
- legacy unstamped tools/tests retain their existing behavior until they enter the cutover path;
- no order authority is introduced.

## Relationship to PRs #757 and #758

The immutable decision, runtime authority map, and ranking-authority taxonomy are retained from PR #757. The integrated tests absorb the useful PR #758 proof themes—purity, contradiction handling, stale/fallback blocking, object support, and protected feed boundaries—without adding a second competing authority contract.
''',
)

write(
    "docs/agent_reviews/runtime_authority_cutover_v1.md",
    r'''# Agent Review — Runtime Authority Cutover V1

## Agent Work Contract

- source_agent: ChatGPT
- action: PROMOTE_RUNTIME_AUTHORITY
- scope: post-PR763 selection, UI, snapshot, and execution-router authority
- forbidden: feed, WebSocket, MEG, persistence, strategy thresholds, broker placement

## Scope Guard

The change is stacked on PR #763 and does not change its branch. Protected feed/MEG paths are forbidden. No live process or broker action is started.

## High-Risk Path Review

The execution router now consumes canonical authority only for candidates stamped by the cutover. This preserves existing legacy tests while ensuring every selected candidate is checked before manual approval or simulation. The LIVE broker path remains unimplemented and no order capability is added.

## Acceptance Proof

- recovered fallback is advisory-only and receives zero selection score/capital;
- stale, missing, unknown, synthetic, and contradictory truth fails closed;
- actual opportunity selector sees executable candidates only;
- operator rows are partitioned by authority;
- execution router blocks authority failures before order-state/approval work;
- protected feed and MEG paths remain untouched.

## What This Does Not Prove

This does not certify PR #763's market-hours packet/bar traversal, profitability, or live broker execution. Those remain separate gates.
''',
)

# A narrow workflow is added separately. The patcher deliberately does not
# modify the PR #763 source branch.
print("runtime authority cutover patch prepared")
