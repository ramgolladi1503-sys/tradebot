#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.repo_forensics.config_loader import ConfigError, load_config
from tools.repo_forensics.critical_module_checker import check_critical_modules
from tools.repo_forensics.evidence_auditor import audit_evidence
from tools.repo_forensics.repo_cartographer import build_repo_map
from tools.repo_forensics.report_writer import write_repo_map_report
from tools.repo_forensics.runtime_wiring import audit_runtime_wiring
from tools.repo_forensics.safety_boundary import audit_safety_boundaries
from tools.repo_forensics.test_reality import classify_tests


DEFAULT_CONFIG = ".gsd-forensics.yaml"
DEFAULT_OUTPUT = "docs/repo_forensics/reports/repo_map_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local, read-only TradeBot repo-forensics checks.")
    parser.add_argument("--repo", default=".", help="Repository root to scan. Default: current directory.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Forensics config path. Default: .gsd-forensics.yaml")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help="Repo map Markdown report path.")
    parser.add_argument(
        "--skip-runtime-wiring",
        action="store_true",
        help="Run only repo cartography. Runtime wiring audit is enabled by default.",
    )
    parser.add_argument(
        "--skip-critical-callers",
        action="store_true",
        help="Skip critical module caller check. Enabled by default.",
    )
    parser.add_argument(
        "--skip-test-reality",
        action="store_true",
        help="Skip test reality classifier. Enabled by default.",
    )
    parser.add_argument(
        "--skip-safety-boundary",
        action="store_true",
        help="Skip safety boundary auditor. Enabled by default.",
    )
    parser.add_argument(
        "--skip-evidence-audit",
        action="store_true",
        help="Skip evidence auditor. Enabled by default.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_root / config_path
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = repo_root / out_path

    try:
        config = load_config(config_path)
        repo_map = build_repo_map(repo_root, config)
        runtime_report = None if args.skip_runtime_wiring else audit_runtime_wiring(repo_root, config)
        critical_report = None if args.skip_critical_callers else check_critical_modules(repo_root, config)
        test_reality_report = None if args.skip_test_reality else classify_tests(repo_root, config)
        safety_report = None if args.skip_safety_boundary else audit_safety_boundaries(repo_root, config)
        evidence_report = None if args.skip_evidence_audit else audit_evidence(repo_root, config)
        report_path = write_repo_map_report(
            repo_map,
            out_path,
            runtime_report=runtime_report,
            critical_report=critical_report,
            test_reality_report=test_reality_report,
            safety_report=safety_report,
            evidence_report=evidence_report,
        )
    except (ConfigError, FileNotFoundError) as exc:
        print(f"[repo-forensics][ERROR] {exc}")
        return 2

    missing_required = len(repo_map.missing_required_entrypoints)
    missing_critical = len(repo_map.missing_critical_modules)
    flow_failures = len(runtime_report.failures) if runtime_report else 0
    flow_unknowns = len(runtime_report.unknowns) if runtime_report else 0
    caller_missing = len(critical_report.missing) if critical_report else 0
    caller_test_only = len(critical_report.test_only) if critical_report else 0
    caller_unreferenced = len(critical_report.unreferenced) if critical_report else 0
    fake_confidence = len(test_reality_report.fake_confidence_tests) if test_reality_report else 0
    unknown_tests = len(test_reality_report.unknown_tests) if test_reality_report else 0
    safety_critical = len(safety_report.critical) if safety_report else 0
    safety_high = len(safety_report.high) if safety_report else 0
    safety_unknown = len(safety_report.unknown) if safety_report else 0
    evidence_high = len(evidence_report.high) if evidence_report else 0
    evidence_medium = len(evidence_report.medium) if evidence_report else 0
    evidence_unknown = len(evidence_report.unknown) if evidence_report else 0
    print(f"[repo-forensics] report={report_path}")
    print(f"[repo-forensics] files={repo_map.inventory.total_files}")
    print(f"[repo-forensics] missing_required_entrypoints={missing_required}")
    print(f"[repo-forensics] missing_critical_modules={missing_critical}")
    print(f"[repo-forensics] runtime_flow_failures={flow_failures}")
    print(f"[repo-forensics] runtime_flow_unknowns={flow_unknowns}")
    print(f"[repo-forensics] critical_caller_missing={caller_missing}")
    print(f"[repo-forensics] critical_caller_test_only={caller_test_only}")
    print(f"[repo-forensics] critical_caller_unreferenced={caller_unreferenced}")
    print(f"[repo-forensics] fake_confidence_tests={fake_confidence}")
    print(f"[repo-forensics] unknown_tests={unknown_tests}")
    print(f"[repo-forensics] safety_critical={safety_critical}")
    print(f"[repo-forensics] safety_high={safety_high}")
    print(f"[repo-forensics] safety_unknown={safety_unknown}")
    print(f"[repo-forensics] evidence_high={evidence_high}")
    print(f"[repo-forensics] evidence_medium={evidence_medium}")
    print(f"[repo-forensics] evidence_unknown={evidence_unknown}")
    if missing_required or missing_critical or flow_failures or caller_missing or caller_test_only or safety_critical or evidence_high:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
