from __future__ import annotations

from pathlib import Path


WRAPPER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_live_with_agent_command_center.sh"


def test_wrapper_script_exists_and_is_executable() -> None:
    assert WRAPPER_PATH.exists()
    assert WRAPPER_PATH.is_file()
    assert WRAPPER_PATH.stat().st_mode & 0o111


def test_wrapper_references_run_live_sh_and_starts_read_only_watcher() -> None:
    text = WRAPPER_PATH.read_text(encoding="utf-8")
    assert "bash \"$ROOT_DIR/run_live.sh\"" in text
    assert "--watch" in text
    assert "--copy-latest true" in text
    assert "--run-id" in text
    assert "--run-dir" in text


def test_wrapper_does_not_contain_dangerous_commands() -> None:
    text = WRAPPER_PATH.read_text(encoding="utf-8")
    forbidden_snippets = [
        "kill -9",
        "rm -f .runtime/locks",
        "rm -rf",
        "unset KITE_ACCESS_TOKEN",
        "broker_api_called",
        "place_order",
        "cancel_order",
        "modify_order",
    ]
    for snippet in forbidden_snippets:
        assert snippet not in text

