from __future__ import annotations

SELF_AUDIT_PREFIXES = (
    "research/option_e2e_recertification_v4/signal_ledger_provenance_v1/",
    "docs/agent_reviews/SIGNAL_LEDGER_PROVENANCE_V1.md",
    "tests/research/option_e2e/test_signal_ledger_provenance",
    ".github/workflows/_temporary_signal_ledger_provenance_evidence.yml",
    "docs/code_excellence/reports/",
)


def is_self_audit_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(normalized == prefix or normalized.startswith(prefix) for prefix in SELF_AUDIT_PREFIXES)


__all__ = ["SELF_AUDIT_PREFIXES", "is_self_audit_path"]
