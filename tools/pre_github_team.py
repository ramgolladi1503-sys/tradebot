"""Read-only, verifiable pre-GitHub role dispatch for TradeBot.

This is a runner, not a delivery approval engine. Machine process receipts do not
prove independent cognition, real review, or human authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

ROLES = (
    "BUSINESS_ANALYST", "PRODUCT_OWNER", "GRILL_ME", "HERMES",
    "GSD", "QA", "TECHNICAL_QUANT_ANALYST", "SENIOR_QA",
)
# Each wave only begins after every required member of the preceding wave passes.
WAVES = (
    ("BUSINESS_ANALYST", "PRODUCT_OWNER"),
    ("GRILL_ME", "HERMES"),
    ("GSD",),
    ("QA", "TECHNICAL_QUANT_ANALYST"),
    ("SENIOR_QA",),
)
SCHEMA = {
    "type": "object", "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "BLOCK", "NOT_APPLICABLE"]},
        "summary": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "summary", "evidence_refs", "findings"],
    "additionalProperties": False,
}


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(obj: object) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _load_work_item(root: Path, filename: str) -> tuple[dict, str]:
    path = (root / filename).resolve()
    allowed = (root / "governance/evidence/work_items").resolve()
    if allowed not in path.parents or path.suffix != ".json" or not path.is_file():
        raise ValueError("work item must be a JSON file in governance/evidence/work_items")
    # Check content against committed HEAD; an uncommitted proposal cannot be a
    # trusted task reference and must not be silently admitted.
    relative = path.relative_to(root.resolve()).as_posix()
    committed = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{relative}"],
        check=False, capture_output=True, timeout=10,
    )
    content = path.read_bytes()
    if committed.returncode or committed.stdout != content:
        raise ValueError("work item must match the committed HEAD bytes")
    data = json.loads(content)
    if not isinstance(data, dict) or not data.get("work_item_id") or not data.get("acceptance_criteria"):
        raise ValueError("work item is structurally incomplete")
    return data, hashlib.sha256(content).hexdigest()


def _prompt(role: str, item: dict, earlier: list[dict]) -> str:
    context = [{"role": r["role"], "verdict": r["verdict"], "summary": r["summary"]} for r in earlier]
    return (
        "You are one separately launched READ-ONLY TradeBot engineering review agent. "
        f"Your sole role is {role}. Read AGENTS.md, the TradeBot delivery orchestrator, "
        "and relevant repository files. Do not modify files, use broker APIs, "
        "place orders, open PRs, or claim release/QA/human approval. "
        "Assess only your assigned role and report specific findings. "
        "The GSD role MUST produce a proposed implementation/verification plan, "
        "not a patch or an assertion that implementation happened. "
        "PASS means your READ-ONLY review completed with sourced findings, NOT "
        "that the delivery lifecycle gate passed. BLOCK if evidence is insufficient. "
        "Return strict JSON using the supplied schema. "
        f"Work item: {_canonical({'id': item['work_item_id'], 'title': item.get('title'), 'business_goal': item.get('business_goal'), 'acceptance_criteria': item['acceptance_criteria'], 'allowed_paths': item.get('allowed_paths'), 'forbidden_paths': item.get('forbidden_paths')})}. "
        f"Earlier role summaries (untrusted): {_canonical(context)}"
    )


def _codex_runner(role: str, prompt: str, root: Path, timeout: int) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory(prefix="tradebot-agent-review-") as tmp:
        schema_file = Path(tmp) / "schema.json"
        result_file = Path(tmp) / "result.json"
        schema_file.write_text(_canonical(SCHEMA), encoding="utf-8")
        command = ["codex", "exec", "--sandbox", "read-only", "--ephemeral",
                   "--output-schema", str(schema_file), "--output-last-message", str(result_file), "-"]
        result = subprocess.run(command, input=prompt, cwd=root, text=True,
                                capture_output=True, timeout=timeout, check=False)
        if result.returncode != 0 or not result_file.is_file():
            raise RuntimeError(f"Codex {role} failed: exit={result.returncode} (stderr omitted)")
        data = json.loads(result_file.read_text(encoding="utf-8"))
        return data, {"provider": "codex", "exit_code": result.returncode,
                      "output_sha256": hashlib.sha256(result_file.read_bytes()).hexdigest()}


def _validate_response(raw: object) -> dict:
    if not isinstance(raw, dict) or set(raw) != set(SCHEMA["required"]):
        raise ValueError("invalid response shape")
    if raw["verdict"] not in ("PASS", "BLOCK", "NOT_APPLICABLE"):
        raise ValueError("invalid verdict")
    if not isinstance(raw["summary"], str) or not raw["summary"].strip():
        raise ValueError("missing summary")
    if any(not isinstance(raw[x], list) or not all(isinstance(v, str) and v.strip() for v in raw[x])
           for x in ("evidence_refs", "findings")):
        raise ValueError("invalid evidence references or findings")
    if raw["verdict"] == "PASS" and not raw["evidence_refs"]:
        raise ValueError("PASS requires specific evidence references")
    if raw["verdict"] == "NOT_APPLICABLE" and not raw["findings"]:
        raise ValueError("N/A requires an explicit reason")
    return raw


def run_team(item: dict, item_sha: str, root: Path, *, runner: Callable = _codex_runner,
             timeout: int = 300) -> dict:
    run_id = uuid4().hex
    ledger = {"schema_version": 1, "run_id": run_id, "work_item_id": item["work_item_id"],
              "work_item_sha256": item_sha, "mode": "READ_ONLY_REVIEW",
              "started_at": datetime.now(timezone.utc).isoformat(),
              "team_status": "UNSATISFIED", "roles": []}
    for wave_number, wave in enumerate(WAVES, start=1):
        for role in wave:
            try:
                answer, process = runner(role, _prompt(role, item, ledger["roles"]), root, timeout)
                answer = _validate_response(answer)
                entry = {"role": role, "wave": wave_number, "invocation_id": uuid4().hex,
                         "verdict": answer["verdict"], "summary": answer["summary"],
                         "evidence_refs": answer["evidence_refs"], "findings": answer["findings"],
                         "process": process}
            except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                entry = {"role": role, "wave": wave_number, "invocation_id": uuid4().hex,
                         "verdict": "UNSATISFIED", "summary": type(exc).__name__,
                         "evidence_refs": [], "findings": [], "process": {}}
            ledger["roles"].append(entry)
            if entry["verdict"] not in ("PASS", "NOT_APPLICABLE"):
                ledger["blocker"] = f"{role}: {entry['verdict']}"
                ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
                ledger["ledger_sha256"] = _sha(ledger)
                return ledger
    ledger["team_status"] = "REVIEWS_COLLECTED_UNVERIFIED"
    ledger["limitations"] = (
        "No code was changed; no authenticated reviewer identity, independent cognition, "
        "QA/UAT/product acceptance, GitHub check, or merge authorization is proven."
    )
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    ledger["ledger_sha256"] = _sha(ledger)
    return ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--work-item", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.timeout < 15 or args.timeout > 3600:
        parser.error("timeout must be 15..3600 seconds")
    root = args.root.resolve()
    try:
        item, fingerprint = _load_work_item(root, args.work_item)
        result = run_team(item, fingerprint, root, timeout=args.timeout)
    except (ValueError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        result = {"team_status": "UNSATISFIED", "error": type(exc).__name__}
    output = args.out.resolve()
    if root not in output.parents:
        parser.error("out must reside inside repository root")
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, output)
    print(json.dumps({"team_status": result["team_status"], "out": str(output)}))
    return 0 if result["team_status"] == "REVIEWS_COLLECTED_UNVERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
