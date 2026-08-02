#!/usr/bin/env python3
"""Install TradeBot dependencies through the verified broker-SDK path.

The ordinary requirements file intentionally excludes KiteConnect and Autobahn.
This installer removes any pre-existing broker SDK graph, installs the base
requirements, builds the hash-verified patched KiteConnect wheel, installs it,
and verifies the resulting environment. It performs no broker authentication or
network API call beyond normal package downloads.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from typing import Iterable

EXPECTED_KITECONNECT_VERSION = "5.2.0+tradebot.1"
EXPECTED_AUTOBAHN_MINIMUM = (25, 10, 2)
PATCHED_WHEEL_NAME = "kiteconnect-5.2.0+tradebot.1-py3-none-any.whl"


def _run(args: Iterable[str], *, cwd: Path) -> None:
    command = [str(part) for part in args]
    print("[tradebot-install]", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _normalized_requirement_name(line: str) -> str:
    text = line.split("#", 1)[0].strip()
    if not text or text.startswith(("-", "http://", "https://", ".", "/")):
        return ""
    for separator in ("===", "==", ">=", "<=", "~=", "!=", ">", "<", "[", ";", " "):
        text = text.split(separator, 1)[0]
    return text.strip().lower().replace("_", "-")


def validate_base_requirements(path: Path) -> None:
    forbidden = {"kiteconnect", "autobahn"}
    found: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        name = _normalized_requirement_name(line)
        if name in forbidden:
            found.append(f"{name}@{line_number}")
    if found:
        raise RuntimeError(
            "Broker SDK dependencies must be installed only through the verified "
            f"installer; forbidden entries: {', '.join(found)}"
        )


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers: list[int] = []
    for component in value.split("."):
        digits = "".join(ch for ch in component if ch.isdigit())
        if not digits:
            break
        numbers.append(int(digits))
    return tuple(numbers)


def verify_installed_broker_sdk() -> dict[str, object]:
    kite_version = metadata.version("kiteconnect")
    autobahn_version = metadata.version("autobahn")
    if kite_version != EXPECTED_KITECONNECT_VERSION:
        raise RuntimeError(
            f"Unexpected KiteConnect version {kite_version}; expected {EXPECTED_KITECONNECT_VERSION}"
        )
    if _version_tuple(autobahn_version) < EXPECTED_AUTOBAHN_MINIMUM:
        raise RuntimeError(
            f"Autobahn {autobahn_version} is below required minimum "
            f"{'.'.join(map(str, EXPECTED_AUTOBAHN_MINIMUM))}"
        )

    patch = json.loads(
        files("kiteconnect").joinpath("TRADEBOT_SECURITY_PATCH.json").read_text(encoding="utf-8")
    )
    if patch.get("upstream_version") != "5.2.0":
        raise RuntimeError("Installed KiteConnect patch has unexpected upstream version")
    if patch.get("patched_version") != EXPECTED_KITECONNECT_VERSION:
        raise RuntimeError("Installed KiteConnect patch has unexpected patched version")
    if patch.get("patch", {}).get("before") != "==19.11.2":
        raise RuntimeError("Installed KiteConnect patch does not prove the vulnerable dependency origin")
    if patch.get("patch", {}).get("after") != ">=25.10.2,<27":
        raise RuntimeError("Installed KiteConnect patch has an unexpected Autobahn constraint")

    return {
        "kiteconnect_version": kite_version,
        "autobahn_version": autobahn_version,
        "patch_provenance": patch,
    }


def install(
    *,
    repo_root: Path,
    requirements: Path,
    download_cache: Path,
    wheel_dir: Path,
    skip_base: bool,
) -> dict[str, object]:
    validate_base_requirements(requirements)
    python = sys.executable

    _run([python, "-m", "pip", "uninstall", "-y", "kiteconnect", "autobahn"], cwd=repo_root)
    if not skip_base:
        _run([python, "-m", "pip", "install", "-r", str(requirements)], cwd=repo_root)

    _run(
        [
            python,
            str(repo_root / "scripts" / "build_secure_kiteconnect_wheel.py"),
            "--download-cache",
            str(download_cache),
            "--output-dir",
            str(wheel_dir),
        ],
        cwd=repo_root,
    )
    wheel_path = wheel_dir / PATCHED_WHEEL_NAME
    if not wheel_path.is_file():
        raise RuntimeError(f"Expected patched wheel was not produced: {wheel_path}")

    _run([python, "-m", "pip", "install", "--force-reinstall", str(wheel_path)], cwd=repo_root)
    _run([python, "-m", "pip", "check"], cwd=repo_root)
    return verify_installed_broker_sdk()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--requirements", type=Path, default=Path("requirements.txt"))
    parser.add_argument("--download-cache", type=Path, default=Path(".runtime/downloads"))
    parser.add_argument("--wheel-dir", type=Path, default=Path(".runtime/wheels"))
    parser.add_argument(
        "--skip-base",
        action="store_true",
        help="Install only the verified broker SDK after focused dependencies were installed separately.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = args.repo_root.expanduser().resolve()

    def resolve_from_root(path: Path) -> Path:
        return path.expanduser().resolve() if path.is_absolute() else (repo_root / path).resolve()

    result = install(
        repo_root=repo_root,
        requirements=resolve_from_root(args.requirements),
        download_cache=resolve_from_root(args.download_cache),
        wheel_dir=resolve_from_root(args.wheel_dir),
        skip_base=bool(args.skip_base),
    )
    print(json.dumps({"status": "PASS", **result}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
