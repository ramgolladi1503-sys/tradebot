from __future__ import annotations


def reconcile(
    records: list[dict[str, object]],
    audit: dict[str, object],
    source_manifest: dict[str, object],
) -> dict[str, object]:
    root_inventory = list(source_manifest.get("root_inventory", []))
    git_searches = list(source_manifest.get("git_searches", []))
    candidates = list(source_manifest.get("candidate_inventory", []))
    unresolved_count = int(source_manifest.get("unresolved_candidate_count", 0))
    accepted_count = int(source_manifest.get("accepted_candidate_count", 0))
    source_status = str(source_manifest.get("conclusion", "SIGNAL_SOURCE_SEARCH_INCOMPLETE"))

    status = "SOURCE_RECONCILIATION_INCOMPLETE"
    if source_status == "SIGNAL_SOURCE_RESOLVED" and accepted_count > 0:
        status = "SOURCE_RECONCILED"
    elif source_status == "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE" and unresolved_count == 0:
        status = "SOURCE_BLOCKER_RECONCILED"

    return {
        "status": status,
        "source_status": source_status,
        "root_count": len(root_inventory),
        "available_root_count": sum(1 for root in root_inventory if root.get("available") and root.get("is_directory")),
        "git_search_count": len(git_searches),
        "git_search_failure_count": sum(
            1 for search in git_searches if search.get("exit_code") != 0 or search.get("timed_out")
        ),
        "candidate_count": len(candidates),
        "accepted_candidate_count": accepted_count,
        "unresolved_candidate_count": unresolved_count,
        "truncated": bool(source_manifest.get("truncated")),
        "signal_count": len(records),
        "legacy_option_replay_audit_record_count": len(audit.get("legacy_option_replay_audit_records", [])),
        "invalidated_historical_record_count": len(audit.get("invalidated_historical_records", [])),
    }
