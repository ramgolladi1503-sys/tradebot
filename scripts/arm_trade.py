from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import argparse
import json
import os
from typing import Optional

from config import config as cfg
from core.approval_store import arm_order_intent
from core.config_approval import check_config_approval
from core.events import write_json_atomic
from core.go_live_scorecard import GoLiveScorecard
from core.paths import logs_dir
from core.review_queue import get_queue_entry, order_payload_hash
from core.time_utils import normalize_epoch_seconds, now_utc_epoch


def _resolve_payload_hash(
    trade_id: Optional[str], payload_hash: Optional[str]
) -> Optional[str]:
    if payload_hash:
        return payload_hash
    if not trade_id:
        return None
    queued = get_queue_entry(trade_id)
    if not queued:
        return None
    return queued.get("approval_payload_hash") or order_payload_hash(queued)


def _confirm_phrase() -> str:
    return str(
        getattr(cfg, "ARMING_CONFIRM_PHRASE", "YES I UNDERSTAND") or "YES I UNDERSTAND"
    )


def _require_recent_health_pass() -> bool:
    return bool(getattr(cfg, "ARMING_REQUIRE_HEALTH_PASS_RECENT", True))


def _health_pass_max_age_sec() -> float:
    return max(60.0, float(getattr(cfg, "ARMING_HEALTH_PASS_MAX_AGE_SEC", 1800.0)))


def _p0_cooldown_sec() -> float:
    return max(60.0, float(getattr(cfg, "ARMING_P0_COOLDOWN_SEC", 1800.0)))


def _cooldown_path():
    default_path = logs_dir() / "arming_cooldown.json"
    path_text = str(
        getattr(cfg, "ARMING_COOLDOWN_STATE_PATH", str(default_path))
        or str(default_path)
    )
    return type(default_path)(path_text)


def _load_json(path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def _record_p0_cooldown(
    *,
    reason_codes: list[str],
    evidence: dict | None = None,
    now_ts: float | None = None,
) -> None:
    now_epoch = float(now_ts if now_ts is not None else now_utc_epoch())
    until_epoch = now_epoch + _p0_cooldown_sec()
    payload = {
        "active": True,
        "reason": "P0_BREACH",
        "reason_codes": list(reason_codes or []),
        "started_ts_epoch": now_epoch,
        "until_ts_epoch": until_epoch,
        "until_ts_iso": None,
        "evidence": dict(evidence or {}),
    }
    try:
        from datetime import datetime, timezone

        payload["until_ts_iso"] = (
            datetime.fromtimestamp(until_epoch, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except Exception:
        payload["until_ts_iso"] = None
    try:
        write_json_atomic(_cooldown_path(), payload)
    except Exception:
        pass


def _cooldown_status(now_ts: float | None = None) -> tuple[bool, float, dict]:
    now_epoch = float(now_ts if now_ts is not None else now_utc_epoch())
    data = _load_json(_cooldown_path())
    if not data:
        return False, 0.0, {}
    if not bool(data.get("active")):
        return False, 0.0, data
    until_epoch = normalize_epoch_seconds(data.get("until_ts_epoch"))
    if until_epoch is None:
        return False, 0.0, data
    remaining = float(until_epoch) - now_epoch
    if remaining <= 0:
        return False, 0.0, data
    return True, remaining, data


def _health_gate_recency_status(now_ts: float | None = None) -> tuple[bool, str, dict]:
    now_epoch = float(now_ts if now_ts is not None else now_utc_epoch())
    path = logs_dir() / "health_gate_report.json"
    if not path.exists():
        return False, "health_gate_report_missing", {"path": str(path)}
    report = _load_json(path)
    if not report:
        return False, "health_gate_report_invalid", {"path": str(path)}
    if not bool(report.get("pass")):
        return (
            False,
            "health_gate_not_passed",
            {"path": str(path), "exit_code": report.get("exit_code")},
        )
    issues = list(report.get("issues") or [])
    p0_issues = [row for row in issues if str((row or {}).get("priority")) == "P0"]
    if p0_issues:
        return (
            False,
            "health_gate_contains_p0",
            {"path": str(path), "p0_count": len(p0_issues)},
        )
    run_ts = normalize_epoch_seconds(report.get("generated_ts"))
    if run_ts is None:
        try:
            run_ts = float(path.stat().st_mtime)
        except Exception:
            run_ts = None
    if run_ts is None:
        return False, "health_gate_timestamp_missing", {"path": str(path)}
    age_sec = max(0.0, now_epoch - float(run_ts))
    max_age = _health_pass_max_age_sec()
    if age_sec > max_age:
        return (
            False,
            "health_gate_pass_too_old",
            {"path": str(path), "age_sec": age_sec, "max_age_sec": max_age},
        )
    return True, "ok", {"path": str(path), "age_sec": age_sec, "max_age_sec": max_age}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Arm a previously approved order intent for live execution."
    )
    parser.add_argument("--trade-id", default=None, help="Trade id in review queue")
    parser.add_argument(
        "--payload-hash",
        default=None,
        help="Direct order intent hash (if not using trade-id)",
    )
    parser.add_argument(
        "--arm-ttl-sec",
        type=int,
        default=None,
        help="Armed window in seconds (defaults to ORDER_ARM_TTL_SEC)",
    )
    parser.add_argument(
        "--confirm-text",
        default=None,
        help='Must exactly match confirmation phrase (default required phrase: "YES I UNDERSTAND").',
    )
    args = parser.parse_args()

    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    payload_hash = _resolve_payload_hash(args.trade_id, args.payload_hash)
    if not payload_hash:
        print(
            "Cannot arm: missing payload hash. Provide --trade-id (queued) or --payload-hash directly."
        )
        return 2

    in_cooldown, remaining_sec, cooldown_data = _cooldown_status()
    if in_cooldown:
        print(
            "ARM blocked: cooldown active after P0 breach. "
            f"remaining_sec={int(remaining_sec)} reason_codes={','.join(list(cooldown_data.get('reason_codes') or []))}"
        )
        return 2

    scorecard = GoLiveScorecard().run(desk_id)
    if str(scorecard.get("status") or "FAIL").upper() != "PASS":
        print(
            "ARM blocked: go-live scorecard failed. "
            f"See {scorecard.get('report_json_path')} and {scorecard.get('report_md_path')}"
        )
        failed_codes = [
            str(item.get("code") or "")
            for item in list(scorecard.get("failures") or [])
        ]
        if failed_codes:
            print(f"Blocking failures: {','.join(failed_codes)}")
            _record_p0_cooldown(
                reason_codes=failed_codes,
                evidence={
                    "source": "go_live_scorecard",
                    "report_json_path": scorecard.get("report_json_path"),
                    "report_md_path": scorecard.get("report_md_path"),
                },
            )
        return 2

    if _require_recent_health_pass():
        health_ok, health_reason, health_evidence = _health_gate_recency_status()
        if not health_ok:
            print(
                f"ARM blocked: health gate recency check failed ({health_reason}). evidence={health_evidence}"
            )
            return 2

    if bool(getattr(cfg, "CONFIG_APPROVAL_ENFORCE_ON_ARM", True)):
        approval = check_config_approval(desk_id=desk_id)
        if not bool(approval.get("ok")):
            print(
                "ARM blocked: config approval mismatch. "
                f"reason={approval.get('reason')} "
                f"approved_hash={approval.get('approved_hash')} "
                f"current_hash={approval.get('current_hash')} "
                f"path={approval.get('path')}"
            )
            return 2

    required_phrase = _confirm_phrase()
    typed = args.confirm_text
    if typed is None:
        typed = input(f'Type "{required_phrase}" to arm LIVE: ').strip()
    if str(typed) != required_phrase:
        print("ARM blocked: confirmation text mismatch.")
        return 2

    actor = os.getenv("USER") or "manual"
    arm_ttl = (
        args.arm_ttl_sec
        if args.arm_ttl_sec is not None
        else int(getattr(cfg, "ORDER_ARM_TTL_SEC", 60))
    )
    ok, reason = arm_order_intent(
        order_intent_hash=payload_hash,
        approver_id=actor,
        channel="cli",
        arm_ttl_sec=arm_ttl,
    )
    if not ok:
        print(f"ARM failed for {payload_hash[:12]}...: {reason}")
        return 2
    print(f"ARMED {payload_hash[:12]}... for {arm_ttl}s window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
