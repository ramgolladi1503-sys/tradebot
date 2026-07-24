from __future__ import annotations


def validate_no_tamper(contract_report: dict[str, object], *_args, **_kwargs) -> bool:
    failures = contract_report.get("failures", []) if isinstance(contract_report, dict) else []
    return bool(contract_report.get("valid") is True and not failures)
