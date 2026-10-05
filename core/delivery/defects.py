from __future__ import annotations

from dataclasses import replace

from .models import Defect, DefectSeverity, DefectStatus


def validate_defect(defect: Defect, work_item_id: str) -> None:
    if defect.work_item_id != work_item_id:
        raise ValueError("defect belongs to a different work item")
    if not defect.defect_id.strip() or not defect.title.strip():
        raise ValueError("defect ID and title are required")
    if not defect.reproduction_steps or not defect.expected_behavior.strip() or not defect.actual_behavior.strip():
        raise ValueError("defect reproduction and expected/actual behavior are required")
    if not defect.evidence:
        raise ValueError("defect evidence is required")
    if defect.status in {DefectStatus.RETEST_PASSED, DefectStatus.CLOSED} and not defect.qa_retest_ref:
        raise ValueError("successful retest requires QA retest evidence")
    if defect.status == DefectStatus.CLOSED and not defect.regression_result.strip():
        raise ValueError("closing a defect requires a regression result")
    if defect.status in {DefectStatus.READY_FOR_RETEST, DefectStatus.RETEST_FAILED,
                         DefectStatus.RETEST_PASSED, DefectStatus.CLOSED} and not defect.developer_fix_ref:
        raise ValueError("retest lifecycle requires a developer fix reference")


def unresolved_severe(defects: tuple[Defect, ...]) -> tuple[Defect, ...]:
    return tuple(d for d in defects if d.severity in {DefectSeverity.S1, DefectSeverity.S2}
                 and d.status != DefectStatus.CLOSED)


def unresolved_required(defects: tuple[Defect, ...]) -> tuple[Defect, ...]:
    # Delivery policy makes S1/S2 mandatory blockers; S3/S4 remain visible but
    # do not invent a trading-risk threshold or block by default.
    return unresolved_severe(defects)


def advance_defect(defect: Defect, target: DefectStatus, *, reference: str = "",
                   regression_result: str = "") -> Defect:
    allowed = {
        DefectStatus.OPEN: {DefectStatus.FIX_IN_PROGRESS},
        DefectStatus.FIX_IN_PROGRESS: {DefectStatus.READY_FOR_RETEST},
        DefectStatus.READY_FOR_RETEST: {DefectStatus.RETEST_FAILED, DefectStatus.RETEST_PASSED},
        DefectStatus.RETEST_FAILED: {DefectStatus.FIX_IN_PROGRESS},
        DefectStatus.RETEST_PASSED: {DefectStatus.CLOSED},
        DefectStatus.CLOSED: set(),
    }
    if target not in allowed[defect.status]:
        raise ValueError(f"invalid defect transition {defect.status.value} -> {target.value}")
    if target == DefectStatus.READY_FOR_RETEST and not reference.strip():
        raise ValueError("developer fix reference is required")
    if target in {DefectStatus.RETEST_FAILED, DefectStatus.RETEST_PASSED} and not reference.strip():
        raise ValueError("QA retest evidence reference is required")
    if target == DefectStatus.CLOSED and not regression_result.strip():
        raise ValueError("regression result is required to close defect")
    updated = replace(defect, status=target,
                      developer_fix_ref=reference if target == DefectStatus.READY_FOR_RETEST else defect.developer_fix_ref,
                      qa_retest_ref=reference if target in {DefectStatus.RETEST_FAILED, DefectStatus.RETEST_PASSED} else defect.qa_retest_ref,
                      regression_result=regression_result if target == DefectStatus.CLOSED else defect.regression_result)
    validate_defect(updated, defect.work_item_id)
    return updated
