from __future__ import annotations

from pathlib import Path


def test_validate_merge_safe_script_has_offline_and_live_gates():
    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_merge_safe.sh"
    text = script.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "--live" in text
    assert "--allow-dirty" in text
    assert "git merge-base --is-ancestor origin/main HEAD" in text
    assert "python -m pytest" in text
    assert "tests/test_option_token_resolver.py" in text
    assert "python scripts/diagnose_no_executable_trades.py logs/" in text
    assert "safe_nearest_contract_fallback" in text
    assert "run_live_safe.sh" in text
