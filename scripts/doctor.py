from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.security_guard import local_token_path, read_local_kite_access_token


@dataclass
class CheckResult:
    name: str
    ok: bool
    reason: str


def _parse_requirements(req_path: Path) -> list[str]:
    if not req_path.exists():
        return []
    deps: list[str] = []
    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        base = line.split(";", 1)[0].strip()
        for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if sep in base:
                base = base.split(sep, 1)[0].strip()
                break
        if base and not base.startswith("-"):
            deps.append(base)
    return deps


def _check_repo_root(repo_root: Path) -> CheckResult:
    cwd = Path.cwd().resolve()
    expected = repo_root.resolve()
    ok = cwd == expected
    if ok:
        return CheckResult("repo_root_cwd", True, f"cwd={cwd}")
    return CheckResult("repo_root_cwd", False, f"cwd={cwd} expected={expected}")


def _check_python_version(min_major: int = 3, min_minor: int = 11) -> CheckResult:
    ver = sys.version_info
    version_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    ok = (ver.major, ver.minor) >= (min_major, min_minor)
    if ok:
        return CheckResult("python_version", True, f"python={version_str}")
    return CheckResult(
        "python_version",
        False,
        f"python={version_str} required>={min_major}.{min_minor}",
    )


def _check_dependencies(repo_root: Path) -> CheckResult:
    req_path = repo_root / "requirements.txt"
    deps = _parse_requirements(req_path)
    if not deps:
        return CheckResult("dependencies", False, f"requirements_missing_or_empty path={req_path}")
    missing: list[str] = []
    for dep in deps:
        try:
            metadata.version(dep)
        except Exception:
            missing.append(dep)
    if missing:
        return CheckResult("dependencies", False, f"missing={','.join(missing)}")
    return CheckResult("dependencies", True, f"installed={len(deps)}")


def _check_token_file_perms() -> CheckResult:
    token_path = local_token_path()
    if not token_path.exists():
        return CheckResult("kite_token_file", False, f"missing path={token_path}")
    mode = stat.S_IMODE(token_path.stat().st_mode)
    if mode != 0o600:
        return CheckResult("kite_token_file", False, f"bad_permissions mode={oct(mode)} expected=0o600 path={token_path}")
    return CheckResult("kite_token_file", True, f"path={token_path} mode=0o600")


def _check_token_conflict() -> CheckResult:
    env_token = os.getenv("KITE_ACCESS_TOKEN", "").strip()
    file_token = read_local_kite_access_token().strip()
    if env_token and file_token and env_token != file_token:
        return CheckResult("kite_token_conflict", False, "env_and_file_tokens_differ")
    if env_token and file_token and env_token == file_token:
        return CheckResult("kite_token_conflict", True, "env_and_file_tokens_match")
    if env_token:
        return CheckResult("kite_token_conflict", True, "env_token_only")
    if file_token:
        return CheckResult("kite_token_conflict", True, "file_token_only")
    return CheckResult("kite_token_conflict", False, "no_token_in_env_or_file")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    checks = [
        _check_repo_root(repo_root),
        _check_python_version(),
        _check_dependencies(repo_root),
        _check_token_file_perms(),
        _check_token_conflict(),
    ]

    print("== TRADING BOT DOCTOR ==")
    for result in checks:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.reason}")

    failed = [c for c in checks if not c.ok]
    if failed:
        print(f"DOCTOR_STATUS=FAIL failed_checks={len(failed)}")
        return 1

    print("DOCTOR_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
