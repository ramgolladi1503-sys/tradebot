from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
INVENTORY = ROOT / "governance/evidence/ENTRYPOINT_INVENTORY.json"
FREEZE_WORKFLOW = WORKFLOWS / "repo-forensics-pr-gate.yml"
REVIEWED_BASE_DISPATCH_PATHS = frozenset({
    ".github/workflows/agentic-qa-evidence-auditor.yml",
    ".github/workflows/agentic-research-integration.yml",
    ".github/workflows/ai-reliability-pr763-certification.yml",
    ".github/workflows/candidate-ml-v2.yml",
    ".github/workflows/cas-closing-auction-shadow-v1.yml",
    ".github/workflows/code-excellence-gates.yml",
    ".github/workflows/feed-resource-soak.yml",
    ".github/workflows/frozen-head-exact-sha-certification.yml",
    ".github/workflows/loop-handoff-gate.yml",
    ".github/workflows/market_story_engine_v1.yml",
    ".github/workflows/meg-shadow-system-certification.yml",
    ".github/workflows/portfolio-ci.yml",
    ".github/workflows/pr782-remaining-evidence-contracts.yml",
    ".github/workflows/pr818-apply-safe-test-contract-repairs.yml",
    ".github/workflows/prospective-market-evidence-v1.yml",
    ".github/workflows/subscription-reconciliation-postclose-v1.yml",
    ".github/workflows/tradebot-mcp.yml",
    ".github/workflows/upstox_offline_v3_repair.yml",
    ".github/workflows/upstox_v3_depth_capture_contract.yml",
})


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _strip_yaml_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == "\\" and quote:
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def _yaml_key(text: str) -> str:
    key = text.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}:
        key = key[1:-1]
    if not key or any(not (char.isascii() and (char.isalnum() or char in "_-")) for char in key):
        raise ValueError(f"unsupported YAML key syntax: {text!r}")
    return key


def _split_flow_entries(text: str) -> list[str]:
    entries: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    pairs = {"[": "]", "{": "}", "(": ")"}
    for index, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\" and quote:
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char in pairs:
            depth += 1
        elif char in pairs.values():
            depth -= 1
            if depth < 0:
                raise ValueError("unsupported unbalanced YAML flow syntax")
        elif char == "," and depth == 0:
            entries.append(text[start:index].strip())
            start = index + 1
    if quote or depth != 0:
        raise ValueError("unsupported unbalanced YAML flow syntax")
    tail = text[start:].strip()
    if tail:
        entries.append(tail)
    elif entries and text.strip().endswith(","):
        # YAML permits a trailing comma in flow collections.
        pass
    elif text.strip():
        entries.append(tail)
    return entries


def _flow_event_key(entry: str) -> str:
    quote: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(entry):
        if escaped:
            escaped = False
        elif char == "\\" and quote:
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == ":" and depth == 0:
            return _yaml_key(entry[:index])
    if quote or depth != 0:
        raise ValueError("unsupported YAML flow entry syntax")
    return _yaml_key(entry)


def _block_event_names(lines: list[str], start: int) -> tuple[set[str], int]:
    first = start
    while first < len(lines):
        content = _strip_yaml_comment(lines[first]).strip()
        if content:
            break
        first += 1
    if first >= len(lines) or not _strip_yaml_comment(lines[first]).strip():
        raise ValueError("empty or unsupported top-level on event block")
    first_line = _strip_yaml_comment(lines[first])
    child_indent = len(first_line) - len(first_line.lstrip(" "))
    if "\t" in first_line[:child_indent] or child_indent == 0:
        raise ValueError("unsupported indentation in top-level on block")
    sequence = first_line.lstrip().startswith("-")
    names: set[str] = set()
    index = first
    while index < len(lines):
        raw = _strip_yaml_comment(lines[index])
        if not raw.strip():
            index += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            break
        if "\t" in raw[:indent]:
            raise ValueError("tabs are unsupported in top-level on block")
        if indent < child_indent:
            break
        if indent > child_indent:
            index += 1
            continue
        entry = raw[indent:].strip()
        if sequence:
            if not entry.startswith("-"):
                raise ValueError("mixed mapping and sequence in top-level on block")
            name = entry[1:].strip()
            if not name or name.startswith(("{", "[", "&", "*", "!")):
                raise ValueError("unsupported sequence event syntax")
            names.add(_yaml_key(name))
        else:
            if entry.startswith("-") or ":" not in entry:
                raise ValueError("unsupported mapping event syntax")
            key, _value = entry.split(":", 1)
            names.add(_yaml_key(key))
        index += 1
    if not names:
        raise ValueError("unsupported empty top-level on block")
    return names, index


def _has_workflow_dispatch(yaml_text: str) -> bool:
    """Parse the supported GitHub `on` trigger shapes using only stdlib code.

    Unsupported syntax raises ValueError so inventory collection fails closed
    instead of silently treating a dispatch workflow as absent.
    """
    lines = yaml_text.splitlines()
    on_entries: list[tuple[int, str]] = []
    for index, original in enumerate(lines):
        raw = _strip_yaml_comment(original)
        if not raw.strip():
            continue
        if raw.startswith((" ", "\t")):
            continue
        if raw.strip() in {"---", "..."}:
            continue
        if ":" not in raw:
            raise ValueError("unsupported top-level YAML syntax")
        key, value = raw.split(":", 1)
        if _yaml_key(key) == "on":
            on_entries.append((index, value))
    if len(on_entries) > 1:
        raise ValueError("duplicate top-level on keys are unsupported")
    if not on_entries:
        return False

    index, value = on_entries[0]
    inline = value.strip()
    if not inline:
        names, _ = _block_event_names(lines, index + 1)
        return "workflow_dispatch" in names
    if inline.startswith("[") and inline.endswith("]"):
        names = {_yaml_key(entry) for entry in _split_flow_entries(inline[1:-1])}
        return "workflow_dispatch" in names
    if inline.startswith("{") and inline.endswith("}"):
        names = {_flow_event_key(entry) for entry in _split_flow_entries(inline[1:-1])}
        return "workflow_dispatch" in names
    if inline.startswith(("&", "*", "!", "|", ">", "[", "{")):
        raise ValueError("unsupported top-level on event syntax")
    scalar = _yaml_key(inline)
    return scalar == "workflow_dispatch"


def _active_dispatch_workflow_paths(directory: Path) -> set[str]:
    return {
        f".github/workflows/{path.name}"
        for path in directory.iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
        if _has_workflow_dispatch(path.read_text(encoding="utf-8"))
    }


def _protected_script() -> str:
    lines = FREEZE_WORKFLOW.read_text(encoding="utf-8").splitlines()
    job_heading = "  pr818-live-flow-freeze-target:"
    step_heading = "      - name: Enforce frozen PR818 live-flow production surface"
    if lines.count(job_heading) != 1 or lines.count(step_heading) != 1:
        raise ValueError("freeze workflow job/step is missing or ambiguous")
    step = lines.index(step_heading)
    run_index = next((index for index in range(step + 1, len(lines))
                      if lines[index].strip() == "run: |"), None)
    if run_index is None:
        raise ValueError("freeze workflow run block is missing")
    body: list[str] = []
    content_indent: int | None = None
    for line in lines[run_index + 1:]:
        if line.strip():
            indent = len(line) - len(line.lstrip(" "))
            if content_indent is None:
                content_indent = indent
            if indent < content_indent:
                break
        body.append(line)
    if content_indent is None or not any(line.strip() for line in body):
        raise ValueError("freeze workflow run block is empty")
    return textwrap.dedent("\n".join(body)).strip("\n")


def _inventory_matches_active(inventory_paths: set[str], scanned_paths: set[str]) -> bool:
    return inventory_paths == scanned_paths


PURPOSE_CLASSES = {
    "TASK_INTAKE",
    "VALIDATION_DIAGNOSTIC",
    "CERTIFICATION_RESEARCH",
    "UNKNOWN",
}
EFFECT_STATUSES = {"DECLARED", "NOT_DECLARED_IN_YAML", "UNKNOWN"}
ACCEPTED_PURPOSE_BY_PATH = {
    ".github/workflows/agentic-qa-evidence-auditor.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/agentic-research-integration.yml": "CERTIFICATION_RESEARCH",
    ".github/workflows/ai-reliability-pr763-certification.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/candidate-ml-v2.yml": "CERTIFICATION_RESEARCH",
    ".github/workflows/cas-closing-auction-shadow-v1.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/code-excellence-gates.yml": "UNKNOWN",
    ".github/workflows/feed-resource-soak.yml": "CERTIFICATION_RESEARCH",
    ".github/workflows/loop-handoff-gate.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/market_story_engine_v1.yml": "CERTIFICATION_RESEARCH",
    ".github/workflows/meg-shadow-system-certification.yml": "CERTIFICATION_RESEARCH",
    ".github/workflows/portfolio-ci.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/pr782-remaining-evidence-contracts.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/prospective-market-evidence-v1.yml": "CERTIFICATION_RESEARCH",
    ".github/workflows/subscription-reconciliation-postclose-v1.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/tradebot-mcp.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/upstox_offline_v3_repair.yml": "VALIDATION_DIAGNOSTIC",
    ".github/workflows/upstox_v3_depth_capture_contract.yml": "VALIDATION_DIAGNOSTIC",
}


def _step_blocks(lines: list[str]):
    """Yield GitHub Actions list-step blocks as (start, end, indent)."""
    starts = []
    for index, line in enumerate(lines):
        match = re.match(r"^( *)-\s+(?:name|uses|run):", line)
        if match:
            starts.append((index, len(match.group(1))))
    for n, (start, indent) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        yield start, end, indent


def _artifact_paths_in_step(lines: list[str], start: int, end: int):
    for index in range(start, end):
        match = re.match(r"^( *)path:\s*(.*?)\s*$", lines[index])
        if not match:
            continue
        indent = len(match.group(1))
        scalar = match.group(2)
        evidence = [{"line": index + 1, "text": lines[index].strip()}]
        if scalar in {"|", "|-", "|+", ">", ">-", ">+"}:
            values = []
            for child in range(index + 1, end):
                raw = lines[child]
                if raw.strip() and len(raw) - len(raw.lstrip(" ")) <= indent:
                    break
                if raw.strip():
                    values.append(raw.strip())
                    evidence.append({"line": child + 1, "text": raw.strip()})
            return values, evidence
        value = scalar.strip("'\"")
        return ([value] if value else []), evidence
    return [], []


def _workflow_yaml_evidence(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines()
    dispatch_lines = [
        i for i, line in enumerate(lines, 1)
        if re.match(r"^\s*workflow_dispatch\s*:", _strip_yaml_comment(line))
    ]
    if len(dispatch_lines) != 1 or not _has_workflow_dispatch(text):
        raise ValueError(f"expected one supported workflow_dispatch trigger in {path}")

    inputs = []
    dispatch_index = dispatch_lines[0] - 1
    dispatch_indent = len(lines[dispatch_index]) - len(lines[dispatch_index].lstrip(" "))
    input_index = next((i for i in range(dispatch_index + 1, len(lines))
                        if re.match(r"^\s+inputs\s*:", lines[i])
                        and len(lines[i]) - len(lines[i].lstrip(" ")) > dispatch_indent), None)
    if input_index is not None:
        input_indent = len(lines[input_index]) - len(lines[input_index].lstrip(" "))
        for i in range(input_index + 1, len(lines)):
            line = lines[i]
            if line.strip() and len(line) - len(line.lstrip(" ")) <= input_indent:
                break
            if len(line) - len(line.lstrip(" ")) == input_indent + 2:
                match = re.match(r"^\s+([A-Za-z0-9_-]+)\s*:", line)
                if match:
                    inputs.append({"name": match.group(1), "line": i + 1, "text": line.strip()})

    checkout_refs = []
    action_network_evidence = []
    artifact_uploads = []
    explicit_network = []
    local_writes = []
    external_mutations = []
    secrets = []
    permission_evidence = []
    code_execution = []
    for start, end, indent in _step_blocks(lines):
        uses_index = next(
            (i for i in range(start, end) if re.match(r"^\s+uses:\s*\S+", lines[i])),
            start if re.match(r"^\s*-\s+uses:\s*\S+", lines[start]) else None,
        )
        uses = re.match(r"^\s*(?:-\s+)?uses:\s*(\S+)", lines[uses_index]) if uses_index is not None else None
        if uses:
            action = uses.group(1)
            if action.startswith("actions/"):
                action_network_evidence.append({"line": uses_index + 1, "text": lines[uses_index].strip()})
            if action.startswith("actions/checkout@"):
                local_writes.append({
                    "line": uses_index + 1,
                    "text": lines[uses_index].strip(),
                    "operation": "checkout action materializes repository content in the runner workspace",
                })
                ref_row = None
                for i in range(start + 1, end):
                    if len(lines[i]) - len(lines[i].lstrip(" ")) <= indent and lines[i].strip():
                        break
                    ref_match = re.match(r"^\s+ref:\s*(.*?)\s*$", lines[i])
                    if ref_match:
                        ref_row = {"line": i + 1, "text": lines[i].strip(), "expression": ref_match.group(1)}
                        break
                checkout_refs.append({
                    "line": uses_index + 1,
                    "text": lines[uses_index].strip(),
                    "ref": ref_row,
                    "default_ref_not_explicit": ref_row is None,
                })
            if action.startswith("actions/upload-artifact@"):
                paths, path_evidence = _artifact_paths_in_step(lines, start, end)
                artifact_uploads.append({
                    "upload_line": uses_index + 1,
                    "upload_text": lines[uses_index].strip(),
                    "paths": paths,
                    "path_evidence": path_evidence,
                })
                external_mutations.append({"line": uses_index + 1, "text": lines[uses_index].strip(), "target": "GitHub Actions artifact store"})
        for i in range(start, end):
            line = lines[i]
            # GitHub Actions permits both mapping-form (`run:` on its own
            # indented line) and compact sequence-form (`- run: command`).
            # Match the latter too; otherwise inline execution is silently
            # omitted from both code-execution and effect evidence.
            if re.match(r"^\s*(?:-\s+)?run:\s*", line):
                code_execution.append({"line": i + 1, "text": line.strip()})
            if re.search(r"\$\{\{\s*secrets\.[A-Za-z_][A-Za-z0-9_]*\s*\}\}", line):
                secrets.append({"line": i + 1, "text": line.strip()})
            if re.search(r"\b(pip install|git fetch|git pull|git lfs|curl\b|wget\b|npm install|https?://)", line, re.I):
                explicit_network.append({"line": i + 1, "text": line.strip()})
            if re.search(r"(--output(?:-dir)?\b|--out\b|mkdir\s+-p|tee\s|git worktree\s+(?:add|remove)|git lfs\s|cat\s*>|(?:^|\s)(?:>>|>)\s*\S+|\btouch\s)", line):
                local_writes.append({"line": i + 1, "text": line.strip()})
            if re.search(r"\bgit push\b|\bgh\s+(?:issue|pr)\b|\bgh api\b|curl.*\s-X\s*(?:POST|PUT|PATCH|DELETE)", line, re.I):
                external_mutations.append({"line": i + 1, "text": line.strip(), "target": "workflow-declared external command"})

    for i, line in enumerate(lines):
        match = re.match(r"^( *)permissions\s*:", line)
        if not match:
            continue
        indent = len(match.group(1))
        permission_evidence.append({"line": i + 1, "text": line.strip()})
        for child in range(i + 1, len(lines)):
            raw_child = lines[child]
            child_indent = len(raw_child) - len(raw_child.lstrip(" "))
            if raw_child.strip() and child_indent <= indent:
                break
            if raw_child.strip():
                permission_evidence.append({"line": child + 1, "text": raw_child.strip()})

    effect_note = (
        "DECLARED records only a YAML declaration; NOT_DECLARED_IN_YAML records only a source scan with no matching declaration. "
        "Neither proves runtime behavior, absence of other effects, safety, or read-only behavior. Invoked code and platform effects may remain UNKNOWN."
    )
    artifact_status = "DECLARED" if artifact_uploads else "NOT_DECLARED_IN_YAML"
    write_status = "DECLARED" if local_writes else "UNKNOWN"
    network_evidence = action_network_evidence + explicit_network
    network_status = "DECLARED" if network_evidence else "UNKNOWN"
    mutation_status = "DECLARED" if external_mutations else ("UNKNOWN" if code_execution else "NOT_DECLARED_IN_YAML")
    secret_status = "DECLARED" if secrets else "NOT_DECLARED_IN_YAML"
    permission_status = "DECLARED" if permission_evidence else "NOT_DECLARED_IN_YAML"

    return {
        "source_evidence": {
            "workflow_sha256": hashlib.sha256(raw).hexdigest(),
            "workflow_dispatch": [{"line": line, "text": lines[line - 1].strip()} for line in dispatch_lines],
            "workflow_dispatch_inputs": inputs,
        },
        "selected_ref_authority": {
            "dispatch_selected_ref_runtime_resolution": "UNKNOWN_FROM_YAML_PLATFORM_CONTEXT",
            "dispatcher_identity": "UNKNOWN_FROM_YAML",
            "checkout_ref_expressions": checkout_refs,
        },
        "candidate_code_execution": {
            "status": "DECLARED" if code_execution else "UNKNOWN",
            "evidence": code_execution,
            "interpretation": "Declared run steps execute workflow code; exact dispatch-ref runtime resolution is not established by YAML.",
        },
        "effects": {
            "artifact_uploads": {"status": artifact_status, "uploads": artifact_uploads, "interpretation": effect_note},
            "local_workspace_writes": {"status": write_status, "evidence": local_writes, "interpretation": effect_note},
            "external_network_api_calls": {
                "status": network_status,
                "evidence": network_evidence,
                "invoked_code_network_behavior": "UNKNOWN",
                "interpretation": effect_note,
            },
            "external_mutation": {"status": mutation_status, "evidence": external_mutations, "interpretation": effect_note},
            "secrets_exposure": {"status": secret_status, "evidence": secrets, "runtime_handling": "UNKNOWN", "interpretation": effect_note},
            "permissions": {
                "status": permission_status,
                "declarations": permission_evidence,
                "effective_permissions": "UNKNOWN",
                "interpretation": effect_note,
            },
        },
    }


def _purpose_evidence_matches(entry: dict, workflow_path: Path) -> bool:
    lines = workflow_path.read_text(encoding="utf-8").splitlines()
    cited = entry.get("purpose_evidence")
    return isinstance(cited, list) and bool(cited) and all(
        isinstance(item, dict)
        and isinstance(item.get("line"), int)
        and 1 <= item["line"] <= len(lines)
        and item.get("text") == lines[item["line"] - 1].strip()
        for item in cited
    )


def _inventory_errors(inventory: dict, workflow_dir: Path = WORKFLOWS, *, scanned_paths: set[str] | None = None) -> list[str]:
    errors = []
    if inventory.get("schema_version") != 3:
        errors.append("INVENTORY_SCHEMA_VERSION_INVALID")
    schema = inventory.get("classification_schema", {})
    if not isinstance(schema, dict) or set(schema.get("purpose_class_values", [])) != PURPOSE_CLASSES:
        errors.append("CLASSIFICATION_SCHEMA_INVALID")
    if not isinstance(schema, dict) or schema.get("accepted_purpose_counts") != {
        "VALIDATION_DIAGNOSTIC": 10,
        "CERTIFICATION_RESEARCH": 6,
        "UNKNOWN": 1,
    }:
        errors.append("ACCEPTED_PURPOSE_COUNTS_INVALID")
    entries = inventory.get("active_workflow_dispatch_entrypoints")
    if not isinstance(entries, list):
        return errors + ["ACTIVE_ENTRYPOINTS_INVALID"]
    paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    if len(paths) != len(entries) or len(paths) != len(set(paths)):
        errors.append("ACTIVE_ENTRYPOINT_PATHS_INVALID")
    if scanned_paths is None:
        try:
            scanned_paths = _active_dispatch_workflow_paths(workflow_dir)
        except (OSError, UnicodeError, ValueError):
            errors.append("DISPATCH_SCAN_FAILED")
            scanned_paths = set()
    if set(paths) != scanned_paths:
        errors.append("ACTIVE_ENTRYPOINT_PATH_PARITY_MISMATCH")

    required = {
        "path", "purpose_class", "review_status", "classification_rationale", "purpose_evidence",
        "prework_admission", "admission_mechanism", "selected_ref_authority", "candidate_code_execution",
        "effects", "source_evidence",
    }
    for entry in entries:
        if not isinstance(entry, dict) or not required <= entry.keys():
            errors.append("ENTRY_CLASSIFICATION_FIELDS_MISSING")
            continue
        path = entry["path"]
        if entry["purpose_class"] not in PURPOSE_CLASSES:
            errors.append(f"ENTRY_PURPOSE_CLASS_INVALID:{path}")
        if ACCEPTED_PURPOSE_BY_PATH.get(path) != entry["purpose_class"]:
            errors.append(f"ENTRY_PURPOSE_MAPPING_MISMATCH:{path}")
        if entry["review_status"] not in {"REVIEWED", "UNREVIEWED"}:
            errors.append(f"ENTRY_REVIEW_STATUS_INVALID:{path}")
        if not isinstance(entry["classification_rationale"], str) or not entry["classification_rationale"].strip():
            errors.append(f"ENTRY_RATIONALE_MISSING:{path}")
        if entry["prework_admission"] != "UNSATISFIED" or entry["admission_mechanism"] is not None:
            errors.append(f"ENTRY_ADMISSION_MUST_REMAIN_UNSATISFIED:{path}")
        if not _purpose_evidence_matches(entry, workflow_dir / Path(path).name):
            errors.append(f"ENTRY_PURPOSE_EVIDENCE_MISMATCH:{path}")
        if entry["purpose_class"] == "UNKNOWN" and entry["review_status"] != "UNREVIEWED":
            errors.append(f"UNKNOWN_PURPOSE_MUST_REMAIN_UNREVIEWED:{path}")
        if entry["purpose_class"] != "UNKNOWN" and entry["review_status"] != "REVIEWED":
            errors.append(f"CLASSIFIED_PURPOSE_REQUIRES_REVIEW:{path}")

        expected = _workflow_yaml_evidence(workflow_dir / Path(path).name)
        if entry["source_evidence"] != expected["source_evidence"]:
            errors.append(f"ENTRY_SOURCE_EVIDENCE_MISMATCH:{path}")
        if entry["selected_ref_authority"] != expected["selected_ref_authority"]:
            errors.append(f"ENTRY_SELECTED_REF_EVIDENCE_MISMATCH:{path}")
        if entry["candidate_code_execution"] != expected["candidate_code_execution"]:
            errors.append(f"ENTRY_CODE_EXECUTION_EVIDENCE_MISMATCH:{path}")
        if entry["effects"] != expected["effects"]:
            errors.append(f"ENTRY_EFFECT_EVIDENCE_MISMATCH:{path}")
        for effect_name, effect in entry.get("effects", {}).items():
            if not isinstance(effect, dict) or effect.get("status") not in EFFECT_STATUSES:
                errors.append(f"ENTRY_EFFECT_STATUS_INVALID:{path}:{effect_name}")

    gaps = inventory.get("repository_gaps", {})
    required_gaps = {
        "universal_platform_intake", "branch_protection_requires_evidence_gate",
        "authenticated_human_identity_approval", "workflow_dispatch_trust_or_prework_gate",
    }
    if not isinstance(gaps, dict) or any(gaps.get(key) != "UNSATISFIED" for key in required_gaps):
        errors.append("REPOSITORY_GAPS_MUST_REMAIN_UNSATISFIED")
    if any(not isinstance(surface, dict) or surface.get("prework_admission") != "UNSATISFIED"
           for surface in inventory.get("other_intake_surfaces", [])):
        errors.append("OTHER_INTAKE_SURFACES_MUST_REMAIN_UNSATISFIED")
    return errors

def _run_protected_script(repo: Path, *, base: str, head: str, head_ref: str):
    env = dict(os.environ)
    env.update({
        "PR_HEAD": head,
        "PR_BASE": base,
        "PR_HEAD_REF": head_ref,
        "PR818_FROZEN_LIVE_SHA": "d7dc45e7c5c76247e7d1b8abd40ec7682fac2f9b",
    })
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _protected_script()],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)
    _git(repo, "push", "origin", "main")
    return _git(repo, "rev-parse", "HEAD")


def test_inventory_covers_active_dispatch_workflows_and_both_retired_triggers():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    actual = _active_dispatch_workflow_paths(WORKFLOWS)
    entries = inventory["active_workflow_dispatch_entrypoints"]
    active = {entry["path"] for entry in entries}
    retired = inventory["retired_workflow_dispatch_entrypoints"]
    retired_paths = {entry["path"] for entry in retired}
    assert inventory["reviewed_base_sha"] == "32e6d77130b748b6644e93376fe948b3cd7b9eb9"
    assert active | retired_paths == REVIEWED_BASE_DISPATCH_PATHS
    assert active.isdisjoint(retired_paths)
    assert active == actual and len(active) == 17
    assert len(retired) == 2
    assert retired[0]["path"] == ".github/workflows/pr818-apply-safe-test-contract-repairs.yml"
    assert retired[0]["status"] == "RETIRED"
    assert retired[0]["evidence"]["pull_request"].endswith("/pull/823")
    assert not (WORKFLOWS / "pr818-apply-safe-test-contract-repairs.yml").exists()
    frozen_head = next(entry for entry in retired if entry["path"].endswith("frozen-head-exact-sha-certification.yml"))
    assert frozen_head["status"] == "RETIRED"
    assert frozen_head["evidence"]["retired_trigger"] == "workflow_dispatch"
    assert frozen_head["evidence"]["workflow_sha256"] == "8d3e077658a21ebf9c812e3ec2235f4cb52249b4e38686e2f82117a32fdf641e"
    assert "efe4dee8c73acae1d8ab5c10a8ad5db8b2ff2bb0" in frozen_head["evidence"]["source"]
    assert "lines 6-16" in frozen_head["evidence"]["source"]
    frozen_text = (WORKFLOWS / "frozen-head-exact-sha-certification.yml").read_text()
    assert _has_workflow_dispatch(frozen_text) is False
    assert "pull_request_target:" in frozen_text
    assert "types: [opened, reopened, synchronize, ready_for_review, edited]" in frozen_text
    assert "inputs." not in frozen_text
    assert "trusted-evidence-coverage:" in frozen_text
    limitations = inventory["limitations"]
    assert any("All 17 active GitHub workflow_dispatch entrypoints remain" in item for item in limitations)
    assert not any("All 18 GitHub workflow_dispatch entrypoints remain" in item for item in limitations)
    assert any("scoped to pull requests targeting main" in item for item in limitations)
    assert all(entry["prework_admission"] == "UNSATISFIED" for entry in entries)
    assert inventory["repository_gaps"]["universal_platform_intake"] == "UNSATISFIED"
    assert inventory["repository_gaps"]["branch_protection_requires_evidence_gate"] == "UNSATISFIED"
    assert inventory["repository_gaps"]["authenticated_human_identity_approval"] == "UNSATISFIED"
    assert _inventory_errors(inventory) == []


def test_workflow_evidence_is_exact_and_code_excellence_multiline_paths_are_parsed():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    for entry in inventory["active_workflow_dispatch_entrypoints"]:
        expected = _workflow_yaml_evidence(WORKFLOWS / Path(entry["path"]).name)
        assert entry["source_evidence"] == expected["source_evidence"]
        assert entry["selected_ref_authority"] == expected["selected_ref_authority"]
        assert entry["candidate_code_execution"] == expected["candidate_code_execution"]
        assert entry["effects"] == expected["effects"]
        assert _purpose_evidence_matches(entry, WORKFLOWS / Path(entry["path"]).name)

    ce = next(e for e in inventory["active_workflow_dispatch_entrypoints"] if e["path"].endswith("code-excellence-gates.yml"))
    uploads = ce["effects"]["artifact_uploads"]["uploads"]
    assert len(uploads) == 1
    assert uploads[0]["paths"] == [
        "docs/code_excellence/reports/post_live_paths.txt",
        "docs/code_excellence/reports/changed_paths.txt",
        "docs/code_excellence/reports/unified_ce_gate_latest.md",
        "docs/code_excellence/reports/unified_agent_elite_latest.md",
    ]
    assert [item["line"] for item in uploads[0]["path_evidence"]] == [153, 154, 155, 156, 157]


def test_inline_run_step_is_declared_and_uncertain_external_mutation_is_not_called_absent(tmp_path):
    # Literal expected evidence intentionally does not use the production
    # scanner as its oracle, so this fixture catches scanner false negatives.
    workflow = tmp_path / "inline.yml"
    workflow.write_text(textwrap.dedent("""\
        name: inline-run-fixture
        on:
          workflow_dispatch:
        jobs:
          check:
            runs-on: ubuntu-latest
            steps:
              - run: ./scripts/may-mutate.sh
    """), encoding="utf-8")
    evidence = _workflow_yaml_evidence(workflow)

    assert evidence["candidate_code_execution"] == {
        "status": "DECLARED",
        "evidence": [{"line": 8, "text": "- run: ./scripts/may-mutate.sh"}],
        "interpretation": "Declared run steps execute workflow code; exact dispatch-ref runtime resolution is not established by YAML.",
    }
    assert evidence["effects"]["external_mutation"]["status"] == "UNKNOWN"
    assert evidence["effects"]["external_mutation"]["evidence"] == []


def test_purpose_class_and_effects_are_orthogonal_and_unknowns_stay_unreviewed():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    entries = inventory["active_workflow_dispatch_entrypoints"]
    classes = {entry["purpose_class"] for entry in entries}
    assert classes == {"VALIDATION_DIAGNOSTIC", "CERTIFICATION_RESEARCH", "UNKNOWN"}
    counts = {purpose: sum(entry["purpose_class"] == purpose for entry in entries) for purpose in PURPOSE_CLASSES}
    assert counts == {"TASK_INTAKE": 0, "VALIDATION_DIAGNOSTIC": 10, "CERTIFICATION_RESEARCH": 6, "UNKNOWN": 1}
    assert {entry["path"]: entry["purpose_class"] for entry in entries} == ACCEPTED_PURPOSE_BY_PATH
    assert all("ARTIFACT_GENERATION" not in entry["purpose_class"] for entry in entries)
    unknown = {Path(e["path"]).name for e in entries if e["purpose_class"] == "UNKNOWN"}
    assert unknown == {"code-excellence-gates.yml"}
    assert all(e["review_status"] == "UNREVIEWED" for e in entries if e["purpose_class"] == "UNKNOWN")
    assert all(e["review_status"] == "REVIEWED" for e in entries if e["purpose_class"] != "UNKNOWN")
    original = entries[0]
    changed_purpose = json.loads(json.dumps(original))
    changed_purpose["purpose_class"] = "CERTIFICATION_RESEARCH"
    assert changed_purpose["effects"] == original["effects"]
    assert changed_purpose["effects"]["artifact_uploads"]["status"] == original["effects"]["artifact_uploads"]["status"]
    assert all(effect["status"] in EFFECT_STATUSES for effect in original["effects"].values())
    assert all("Neither proves runtime behavior, absence of other effects, safety, or read-only behavior" in effect["interpretation"] for effect in original["effects"].values())


def test_inventory_rejects_missing_invalid_or_unverified_evidence():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

    missing = json.loads(json.dumps(inventory))
    del missing["active_workflow_dispatch_entrypoints"][0]["effects"]["permissions"]["status"]
    assert any(code.startswith("ENTRY_EFFECT_EVIDENCE_MISMATCH:") for code in _inventory_errors(missing))

    invalid_class = json.loads(json.dumps(inventory))
    invalid_class["active_workflow_dispatch_entrypoints"][0]["purpose_class"] = "PASS"
    assert any(code.startswith("ENTRY_PURPOSE_CLASS_INVALID:") for code in _inventory_errors(invalid_class))

    wrong_accepted_class = json.loads(json.dumps(inventory))
    wrong_entry = next(e for e in wrong_accepted_class["active_workflow_dispatch_entrypoints"]
                       if e["path"].endswith("ai-reliability-pr763-certification.yml"))
    wrong_entry["purpose_class"] = "CERTIFICATION_RESEARCH"
    assert any(code.startswith("ENTRY_PURPOSE_MAPPING_MISMATCH:") for code in _inventory_errors(wrong_accepted_class))

    invalid_effect = json.loads(json.dumps(inventory))
    invalid_effect["active_workflow_dispatch_entrypoints"][0]["effects"]["permissions"]["status"] = "SAFE"
    assert any(code.startswith("ENTRY_EFFECT_EVIDENCE_MISMATCH:") for code in _inventory_errors(invalid_effect))

    promoted = json.loads(json.dumps(inventory))
    promoted["active_workflow_dispatch_entrypoints"][0]["prework_admission"] = "SATISFIED"
    assert any(code.startswith("ENTRY_ADMISSION_MUST_REMAIN_UNSATISFIED:") for code in _inventory_errors(promoted))


def test_inventory_rejects_workflow_hash_drift():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    inventory["active_workflow_dispatch_entrypoints"][0]["source_evidence"]["workflow_sha256"] = "0" * 64
    assert any(code.startswith("ENTRY_SOURCE_EVIDENCE_MISMATCH:") for code in _inventory_errors(inventory))


def test_inventory_rejects_unlisted_new_dispatch_path():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    actual = _active_dispatch_workflow_paths(WORKFLOWS)
    actual.add(".github/workflows/new-unreviewed-dispatch.yml")
    assert "ACTIVE_ENTRYPOINT_PATH_PARITY_MISMATCH" in _inventory_errors(inventory, scanned_paths=actual)


def test_dispatch_scanner_handles_event_shorthand_and_unlisted_workflow(tmp_path):
    sequence_form = "name: sequence\non: [push, workflow_dispatch]\njobs: {}\n"
    inline_mapping_form = "name: mapping\non: {push: {}, workflow_dispatch: {}}\njobs: {}\n"
    mapping_form = "name: block mapping\non:\n  push:\n  workflow_dispatch:\njobs: {}\n"
    scalar_form = "name: scalar\non: workflow_dispatch\njobs: {}\n"
    quoted_scalar_form = "name: quoted scalar\non: 'workflow_dispatch'\njobs: {}\n"
    quoted_sequence_form = 'name: quoted sequence\non: ["push", \'workflow_dispatch\']\njobs: {}\n'
    non_dispatch_scalar = "name: another trigger\non: push\njobs: {}\n"
    assert _has_workflow_dispatch(sequence_form)
    assert _has_workflow_dispatch(inline_mapping_form)
    assert _has_workflow_dispatch(mapping_form)
    assert _has_workflow_dispatch(scalar_form)
    assert _has_workflow_dispatch(quoted_scalar_form)
    assert _has_workflow_dispatch(quoted_sequence_form)
    assert not _has_workflow_dispatch(non_dispatch_scalar)

    for unsupported in (
        "name: alias\non: *shared_events\njobs: {}\n",
        "name: folded\non: |\n  workflow_dispatch\njobs: {}\n",
        "name: malformed\non: [push, workflow_dispatch\njobs: {}\n",
        "name: malformed scalar\non: workflow_dispatch: extra\njobs: {}\n",
        "name: malformed sequence key\non: [workflow_dispatch: extra]\njobs: {}\n",
        "name: malformed sequence token\non: [workflow_dispatch extra]\njobs: {}\n",
        "name: duplicate on\non: push\non: workflow_dispatch\njobs: {}\n",
    ):
        try:
            _has_workflow_dispatch(unsupported)
        except ValueError:
            pass
        else:
            raise AssertionError("unsupported trigger YAML must fail closed")

    new_workflow = tmp_path / "unlisted.yml"
    new_workflow.write_text(sequence_form, encoding="utf-8")
    scanned_with_new_workflow = _active_dispatch_workflow_paths(WORKFLOWS) | _active_dispatch_workflow_paths(tmp_path)
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    recorded_active = {entry["path"] for entry in inventory["active_workflow_dispatch_entrypoints"]}
    assert not _inventory_matches_active(recorded_active, scanned_with_new_workflow)


def test_protected_freeze_gate_compares_pr_delta_without_failing_on_old_base_drift(tmp_path):
    repo = tmp_path / "repo"
    bare = tmp_path / "remote.git"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "core/feed").mkdir(parents=True)
    (repo / "core/feed/frozen.py").write_text("VALUE = 0\n", encoding="utf-8")
    old_baseline = _commit(repo, "old baseline")
    (repo / "core/feed/frozen.py").write_text("VALUE = 1\n", encoding="utf-8")
    drifted_base = _commit(repo, "already present on base")

    # Existing protected-path drift between the old baseline and PR base is
    # deliberately ignored; the base-to-head PR delta is empty and passes.
    passed = _run_protected_script(repo, base=drifted_base, head=drifted_base, head_ref="topic")
    assert passed.returncode == 0, passed.stderr + passed.stdout
    assert "PR818_FROZEN_LIVE_FLOW_PRESERVED" in passed.stdout

    (repo / "core/feed/frozen.py").write_text("VALUE = 2\n", encoding="utf-8")
    protected_head = _commit(repo, "protected path changed in PR")
    failed = _run_protected_script(repo, base=drifted_base, head=protected_head, head_ref="topic")
    assert failed.returncode != 0
    assert "PR818_FROZEN_LIVE_FLOW_VIOLATION" in failed.stdout
    assert "core/feed/frozen.py" in failed.stdout

    (repo / ".github/workflows").mkdir(parents=True)
    freeze_file = repo / ".github/workflows/repo-forensics-pr-gate.yml"
    freeze_file.write_text("name: governed workflow edit\n", encoding="utf-8")
    bootstrap_head = _commit(repo, "workflow bootstrap edit")
    bootstrap = _run_protected_script(
        repo,
        base=protected_head,
        head=bootstrap_head,
        head_ref="governance/freeze-pr818-live-flow-finalize-v1",
    )
    assert bootstrap.returncode == 0, bootstrap.stderr + bootstrap.stdout
    assert "PR818_FREEZE_BOOTSTRAP_FINALIZE_ONLY" in bootstrap.stdout

    ordinary_branch = _run_protected_script(
        repo, base=protected_head, head=bootstrap_head, head_ref="topic"
    )
    assert ordinary_branch.returncode != 0
    assert "PR818_FROZEN_LIVE_FLOW_VIOLATION" in ordinary_branch.stdout

    script = _protected_script()
    assert "PR818_FROZEN_MAIN_BASELINE" not in script
    assert "PR818_FROZEN_MAIN_BASELINE_DRIFT" not in script
    assert "git diff --name-only \"$PR_BASE\" \"$PR_HEAD\"" in script
    assert old_baseline != drifted_base
