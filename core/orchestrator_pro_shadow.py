from __future__ import annotations

import logging
from collections.abc import Mapping

from config import config as cfg
from core.events import write_json_atomic
from core.paths import logs_dir
from core.pro_strategy_pipeline import run_pro_strategy_pipeline


logger = logging.getLogger(__name__)


def pro_shadow_report_path(loop_id: str) -> str:
    return str(logs_dir() / f"pro_strategy_shadow_{loop_id or 'latest'}.json")


def sanitize_pro_shadow_rows(market_data_list: list[dict] | None) -> list[dict]:
    safe_rows: list[dict] = []
    for raw in list(market_data_list or []):
        try:
            if isinstance(raw, Mapping):
                safe_rows.append(dict(raw))
            elif isinstance(raw, dict):
                safe_rows.append(dict(raw))
            else:
                safe_rows.append({"value": str(raw)})
        except Exception:
            if isinstance(raw, Mapping):
                safe_rows.append(dict(raw))
            elif isinstance(raw, dict):
                safe_rows.append(dict(raw))
            else:
                safe_rows.append({"value": str(raw)})
    return safe_rows


def build_pro_shadow_report(report: dict, *, loop_id: str, started_at: float) -> dict:
    candidate_preview = []
    for candidate in list(report.get("candidates") or [])[:3]:
        if not isinstance(candidate, dict):
            continue
        candidate_preview.append(
            {
                "symbol": str(candidate.get("symbol") or "UNKNOWN").upper(),
                "family": str(
                    candidate.get("strategy_family")
                    or candidate.get("signal_family")
                    or candidate.get("family")
                    or candidate.get("strategy")
                    or candidate.get("source")
                    or ""
                ).strip()[:24],
                "score": candidate.get("final_score"),
            }
        )
    error_preview = [str(err)[:120] for err in list(report.get("errors") or [])[:3]]
    return {
        "loop_id": loop_id,
        "started_at": started_at,
        "enabled": bool(report.get("enabled", False)),
        "strict_mode": bool(getattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", True)),
        "candidate_count": len(report.get("candidates") or []),
        "error_count": len(report.get("errors") or []),
        "candidate_preview": candidate_preview,
        "error_preview": error_preview,
        "report": report,
    }


def run_pro_shadow_pipeline_worker_entry(market_data_list: list[dict] | None, loop_id: str, started_at: float) -> None:
    report: dict[str, object] = {
        "enabled": True,
        "flags": {},
        "candidates": [],
        "errors": [],
    }
    try:
        report = run_pro_strategy_pipeline(market_data_list, now_ts=started_at)
    except Exception as exc:
        logger.exception("pro_shadow_pipeline_failed err=%s", exc)
        report = {
            "enabled": True,
            "flags": {},
            "candidates": [],
            "errors": [f"pro_shadow_pipeline_failed:{type(exc).__name__}:{exc}"],
        }
    shadow_report = build_pro_shadow_report(report, loop_id=loop_id, started_at=started_at)
    try:
        write_json_atomic(pro_shadow_report_path(loop_id), shadow_report)
    except Exception as exc:
        logger.warning("pro_shadow_report_write_failed err=%s", exc)
    finally:
        logger.info(
            "pro_strategy_shadow_summary enabled=%s candidates=%s errors=%s strict_mode=%s loop_id=%s candidate_preview=%s error_preview=%s",
            bool(report.get("enabled", False)),
            len(report.get("candidates") or []),
            len(report.get("errors") or []),
            bool(getattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", True)),
            loop_id,
            shadow_report.get("candidate_preview"),
            shadow_report.get("error_preview"),
        )


def create_pro_shadow_process(market_data_list: list[dict] | None, loop_id: str, started_at: float):
    import multiprocessing

    ctx = multiprocessing.get_context("spawn")
    return ctx.Process(
        target=run_pro_shadow_pipeline_worker_entry,
        args=(market_data_list, loop_id, started_at),
        name=f"pro-shadow-{loop_id or 'cycle'}",
        daemon=True,
    )

