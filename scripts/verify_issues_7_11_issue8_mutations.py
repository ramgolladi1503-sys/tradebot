#!/usr/bin/env python3
"""Kill targeted Issue 8 CAS identity mutants in isolated temporary copies.

This validation tool copies only the CAS producer and its focused test file to
a temporary directory, mutates one guard at a time, and runs the corresponding
test. It does not edit the checkout, access market data, or invoke runtime,
broker, or order paths.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


MUTANTS = (
    (
        "missing_expected_token_wildcard",
        ((
            "expected_token_valid = type(expected_token) is int and expected_token > 0",
            "expected_token_valid = expected_token is None or (type(expected_token) is int and expected_token > 0)",
        ),),
        "test_capture_with_missing_expected_token_never_persists_captured_primitive",
    ),
    (
        "remove_nifty_identity_guard",
        ((
            'if row.get("underlying_symbol") != "NIFTY": return False,"identity"',
            'if False: return False,"identity"',
        ),),
        "test_primitive_verifier_rejects_self_consistent_wrong_underlying_identity",
    ),
    (
        "allow_bool_capture_token",
        (
            ("type(tick_token) is int and tick_token > 0", "isinstance(tick_token, int) and tick_token > 0"),
            ("type(payload_token) is int and payload_token > 0", "isinstance(payload_token, int) and payload_token > 0"),
        ),
        "test_capture_rejects_self_consistent_malformed_instrument_tokens[True]",
    ),
    (
        "allow_bool_persisted_row_token",
        ((
            "type(row_token) is not int or row_token != underlying_token",
            "not isinstance(row_token, int) or row_token != underlying_token",
        ),),
        "test_verifier_rejects_malformed_persisted_row_tokens[True]",
    ),
    (
        "allow_bool_verified_payload_token",
        ((
            "type(event_token) is not int or event_token <= 0",
            "not isinstance(event_token, int) or event_token <= 0",
        ),),
        "test_verifier_rejects_self_consistent_malformed_event_tokens[True]",
    ),
    (
        "remove_source_event_id_type_guard",
        ((
            "isinstance(source_event_id, str) and bool(source_event_id)",
            "bool(source_event_id)",
        ),),
        "test_malformed_source_event_ids_block_capture_without_raising",
    ),
)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "cas_primitive_producer.py"
    test_path = repo / "tests" / "test_cas_primitive_producer.py"
    source = source_path.read_text(encoding="utf-8")
    current_tests = test_path.read_text(encoding="utf-8")

    with TemporaryDirectory(prefix="issues711_issue8_mutation_") as temp_dir:
        temp_root = Path(temp_dir)
        temp_core = temp_root / "core"
        temp_tests = temp_root / "tests"
        temp_core.mkdir()
        temp_tests.mkdir()
        (temp_core / "__init__.py").write_text("", encoding="utf-8")
        (temp_tests / "test_cas_primitive_producer.py").write_text(current_tests, encoding="utf-8")
        mutant_module = temp_core / "cas_primitive_producer.py"

        env = os.environ.copy()
        prior_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(temp_root) + (os.pathsep + prior_pythonpath if prior_pythonpath else "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        test_file = str(temp_tests / "test_cas_primitive_producer.py")

        for name, replacements, test_name in MUTANTS:
            mutated = source
            for original, replacement in replacements:
                if original not in mutated:
                    print(f"ERROR: mutation anchor missing for {name}: {original!r}", file=sys.stderr)
                    return 2
                mutated = mutated.replace(original, replacement, 1)
            pycache = temp_core / "__pycache__"
            if pycache.exists():
                for cached_file in pycache.iterdir():
                    cached_file.unlink()
            mutant_module.write_text(mutated, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", f"{test_file}::{test_name}"],
                cwd=temp_root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            if result.returncode == 0:
                print(f"SURVIVED: {name}", file=sys.stderr)
                print(result.stdout[-2000:], file=sys.stderr)
                return 1
            if test_name.split("[", 1)[0] not in result.stdout:
                print(f"INVALID MUTATION RESULT: {name}; targeted test did not appear in output", file=sys.stderr)
                print(result.stdout[-2000:], file=sys.stderr)
                return 2
            print(f"KILLED: {name}")

    print(f"PASS: {len(MUTANTS)}/{len(MUTANTS)} targeted mutants killed; temporary copies removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
