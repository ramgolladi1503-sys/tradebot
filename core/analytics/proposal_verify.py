from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except Exception:
        return None


def load_json(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file_not_found:{p}")
    if not p.is_file():
        raise ValueError(f"not_a_file:{p}")
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid_json:{p}:{type(exc).__name__}:{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected_json_object:{p}")
    return dict(payload)


def load_snapshot(path: Path) -> dict:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except Exception as exc:
            raise ValueError(
                f"yaml_not_supported:{p}:PyYAML not installed; provide JSON snapshot instead"
            ) from exc
        if not p.exists():
            raise FileNotFoundError(f"file_not_found:{p}")
        if not p.is_file():
            raise ValueError(f"not_a_file:{p}")
        try:
            payload = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"invalid_yaml:{p}:{type(exc).__name__}:{exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"expected_yaml_object:{p}")
        return dict(payload)
    return load_json(p)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write(path, json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True) + "\n")


def _flatten_snapshot(snapshot: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in snapshot.items():
        key = str(raw_key)
        dotted = f"{prefix}.{key}" if prefix else key
        out[dotted] = value
        if isinstance(value, Mapping):
            out.update(_flatten_snapshot(value, dotted))
            if key not in out:
                out[key] = value
    return out


def _lookup_snapshot(snapshot: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    if key in snapshot:
        return True, snapshot[key]

    flattened = _flatten_snapshot(snapshot)
    if key in flattened:
        return True, flattened[key]

    # bonus lookup: dotted key path traversal
    if "." in key:
        cur: Any = snapshot
        ok = True
        for part in key.split("."):
            if isinstance(cur, Mapping) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            return True, cur

    # bonus lookup: find exact key leaf anywhere in nested snapshot
    for flat_key, value in flattened.items():
        if flat_key.split(".")[-1] == key:
            return True, value

    return False, None


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _check_type_match(observed: Any, proposed: Any) -> tuple[str, str]:
    if observed is None:
        return "WARN", "snapshot value is null; type confidence is low"

    if isinstance(observed, bool):
        if isinstance(proposed, bool):
            return "PASS", "bool type matches"
        return "FAIL", f"type mismatch: expected bool got {_type_name(proposed)}"

    # numeric compatibility: int/float are compatible (but not bool)
    obs_is_num = isinstance(observed, (int, float)) and not isinstance(observed, bool)
    prop_is_num = isinstance(proposed, (int, float)) and not isinstance(proposed, bool)
    if obs_is_num:
        if prop_is_num:
            return "PASS", "numeric type compatible"
        return "FAIL", f"type mismatch: expected numeric got {_type_name(proposed)}"

    if isinstance(observed, str):
        if isinstance(proposed, str):
            return "PASS", "string type matches"
        return "FAIL", f"type mismatch: expected str got {_type_name(proposed)}"

    if isinstance(observed, list):
        if isinstance(proposed, list):
            return "PASS", "list type matches"
        return "FAIL", f"type mismatch: expected list got {_type_name(proposed)}"

    if isinstance(observed, dict):
        if isinstance(proposed, dict):
            return "PASS", "dict type matches"
        return "FAIL", f"type mismatch: expected dict got {_type_name(proposed)}"

    if type(observed) is type(proposed):
        return "PASS", "type matches"
    return "FAIL", f"type mismatch: expected {_type_name(observed)} got {_type_name(proposed)}"


def _check_value_range(key: str, proposed: Any) -> tuple[str, str]:
    key_upper = key.upper()
    prop_num = _safe_float(proposed)

    if "SPREAD" in key_upper:
        if prop_num is None:
            return "FAIL", "spread-like key requires numeric proposed value"
        if prop_num > 0.10:
            return "FAIL", f"spread value {prop_num} exceeds hard fail threshold 0.10"
        if prop_num < 0.0001 or prop_num > 0.05:
            return "WARN", f"spread value {prop_num} outside expected range 0.0001..0.05"
        return "PASS", "spread value within expected range"

    if "AGE" in key_upper or "STALE" in key_upper:
        if prop_num is None:
            return "FAIL", "age/stale-like key requires numeric proposed value"
        if prop_num > 300:
            return "FAIL", f"age value {prop_num} exceeds hard fail threshold 300"
        if prop_num < 0.1 or prop_num > 60:
            return "WARN", f"age value {prop_num} outside expected range 0.1..60"
        return "PASS", "age value within expected range"

    if "WINDOW" in key_upper:
        prop_int = _safe_int(proposed)
        if prop_int is None:
            return "FAIL", "window-like key requires integer proposed value"
        if prop_int > 5000:
            return "FAIL", f"window value {prop_int} exceeds hard fail threshold 5000"
        if prop_int < 1 or prop_int > 500:
            return "WARN", f"window value {prop_int} outside expected range 1..500"
        return "PASS", "window value within expected range"

    return "PASS", "no heuristic"


def _check_scope_rule(
    *,
    scope: str,
    window_days: int | None,
    sessions: int | None,
    effect_size: float | None,
    sample_size: int | None,
) -> tuple[str, str]:
    normalized = _text(scope).upper()
    ses = int(sessions or 0)
    eff = float(effect_size or 0.0)
    sample = int(sample_size or 0)

    if normalized == "PAPER_ONLY":
        return "PASS", "paper scope always allowed"

    if normalized == "LIVE_CANDIDATE":
        if ses >= 3 and sample >= 50:
            return "PASS", "live_candidate requirements satisfied"
        return "FAIL", f"live_candidate requires sessions>=3 and sample_size>=50 (got sessions={ses}, sample={sample})"

    if normalized == "LIVE":
        if window_days is None:
            return "FAIL", "window_days missing; LIVE scope blocked"
        if window_days >= 5 and ses >= 5 and eff >= 0.20 and sample >= 100:
            return "PASS", "LIVE strict requirements satisfied"
        return (
            "FAIL",
            "LIVE requires window_days>=5, sessions>=5, effect_size>=0.20, sample_size>=100 "
            f"(got window_days={window_days}, sessions={ses}, effect_size={eff}, sample_size={sample})",
        )

    return "FAIL", f"unknown scope:{scope}"


def verify_proposal(proposal: dict, snapshot: dict) -> dict:
    proposal_obj = dict(proposal or {})
    snapshot_obj = dict(snapshot or {})

    items = list(proposal_obj.get("proposals") or [])
    window_days_raw = proposal_obj.get("window_days")
    window_days = _safe_int(window_days_raw)

    results: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    warn_count = 0

    for item in items:
        row = dict(item or {})
        change = dict(row.get("change") or {})
        key = _text(change.get("key"))
        proposed = change.get("proposed")
        scope = _text(change.get("scope")).upper()
        just = dict(row.get("justification") or {})
        sample_size = _safe_int(just.get("sample_size"))
        effect_size = _safe_float(just.get("effect_size"))
        sessions = _safe_int(just.get("sessions"))

        checks: list[dict[str, str]] = []

        exists, observed = _lookup_snapshot(snapshot_obj, key)
        if exists:
            checks.append({"name": "key_exists", "status": "PASS", "details": f"key found in snapshot: {key}"})
        else:
            checks.append({"name": "key_exists", "status": "FAIL", "details": f"unknown key: {key}"})

        if exists:
            type_status, type_details = _check_type_match(observed, proposed)
        else:
            type_status, type_details = ("FAIL", "type check skipped because key missing")
        checks.append({"name": "type_match", "status": type_status, "details": type_details})

        range_status, range_details = _check_value_range(key, proposed)
        checks.append({"name": "value_range", "status": range_status, "details": range_details})

        scope_status, scope_details = _check_scope_rule(
            scope=scope,
            window_days=window_days,
            sessions=sessions,
            effect_size=effect_size,
            sample_size=sample_size,
        )
        checks.append({"name": "scope_rule", "status": scope_status, "details": scope_details})

        statuses = {check["status"] for check in checks}
        if "FAIL" in statuses:
            row_status = "FAIL"
            fail_count += 1
        elif "WARN" in statuses:
            row_status = "WARN"
            warn_count += 1
        else:
            row_status = "PASS"
            pass_count += 1

        result_row = {
            "id": _text(row.get("id")) or "unknown_id",
            "key": key,
            "status": row_status,
            "checks": checks,
            "observed_current": observed if exists else None,
            "proposed": proposed,
            "notes": _text(row.get("notes")),
        }
        results.append(result_row)

    if fail_count > 0:
        overall = "FAIL"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "proposal_path": _text(proposal_obj.get("proposal_path")),
        "snapshot_path": _text(proposal_obj.get("snapshot_path")),
        "status": overall,
        "summary": {
            "total_proposals": len(items),
            "passed": pass_count,
            "failed": fail_count,
            "warnings": warn_count,
        },
        "results": results,
    }


def render_verification_md(report: dict) -> str:
    summary = dict((report or {}).get("summary") or {})
    results = list((report or {}).get("results") or [])

    lines: list[str] = []
    lines.append("# Proposal Verification Report")
    lines.append("")
    lines.append(f"- status: {_text((report or {}).get('status')) or 'UNKNOWN'}")
    lines.append(f"- proposal_path: {_text((report or {}).get('proposal_path'))}")
    lines.append(f"- snapshot_path: {_text((report or {}).get('snapshot_path'))}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- total_proposals: {int(summary.get('total_proposals') or 0)}")
    lines.append(f"- passed: {int(summary.get('passed') or 0)}")
    lines.append(f"- failed: {int(summary.get('failed') or 0)}")
    lines.append(f"- warnings: {int(summary.get('warnings') or 0)}")
    lines.append("")
    lines.append("## Results")
    if not results:
        lines.append("- No proposals to verify.")
    for idx, row in enumerate(results, start=1):
        lines.append(f"{idx}. **{_text(row.get('id'))}** key=`{_text(row.get('key'))}` status={_text(row.get('status'))}")
        lines.append(f"   - observed_current: {json.dumps(row.get('observed_current'), ensure_ascii=True)}")
        lines.append(f"   - proposed: {json.dumps(row.get('proposed'), ensure_ascii=True)}")
        checks = list(row.get("checks") or [])
        for check in checks:
            lines.append(
                f"   - check `{_text(check.get('name'))}`: {_text(check.get('status'))} - {_text(check.get('details'))}"
            )
        note = _text(row.get("notes"))
        if note:
            lines.append(f"   - notes: {note}")
    lines.append("")
    return "\n".join(lines)


def write_verification(report: dict, out_dir: Path) -> tuple[Path, Path]:
    base = Path(out_dir)
    md_path = base / "verification_report.md"
    json_path = base / "verification_report.json"
    _atomic_write(md_path, render_verification_md(report))
    _atomic_write_json(json_path, report)
    return md_path, json_path
