"""Fail-closed local source audit for the remaining option-E2E authority gaps."""

from .build_evidence import build
from .root_scan import RootSpec, parse_root_spec, scan_declared_roots
from .trace_audit import audit_execution_entry_trace

__all__ = [
    "RootSpec",
    "audit_execution_entry_trace",
    "build",
    "parse_root_spec",
    "scan_declared_roots",
]
