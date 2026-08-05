import os
import subprocess
import sys
from pathlib import Path


def test_child_rejects_missing_frozen_marker_before_observation_runtime(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    plan_root = Path("/Users/madhuram/tradebot-live-supervision/kite/meg-launch-plan-determinism-repair-20260805-01/launch_plan_freeze")
    command = [
        sys.executable, "-B", "scripts/run_kite_read_only_observation_v1.py",
        "--session-date", "2026-08-05", "--output-root", str(tmp_path),
        "--kite-instruments-file", "runtime/reference/market_event_graph/kite_instruments/kite_nse_instruments_828c0c378e493972.json",
        "--launch-plan", str(plan_root / "launch_plan.json"),
        "--frozen-launch-plan", str(plan_root / "launch_plan.json"),
        "--expected-semantic-sha256", "3e621567754721c448bd0f5d59ee88ab8f4abd9067a673bc34fe9a337e6a662b",
        "--expected-resolver-snapshot-sha256", "c553bab66cf028b92f703d3e9ff5e11650de548ac3fd1e3bdb2a651bca8e0b6d",
        "--campaign-id", "meg-launch-plan-determinism-proof-20260805-01",
        "--token-path", "/Users/madhuram/tradebot/.runtime/kite_access_token",
    ]
    marker = plan_root / "FROZEN"
    moved = plan_root / "FROZEN.test-hidden"
    marker.rename(moved)
    try:
        env = dict(os.environ)
        result = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True)
    finally:
        moved.rename(marker)
    assert result.returncode != 0
    assert "FROZEN_MARKER_MISSING" in result.stderr or "FROZEN_MARKER_MISSING" in result.stdout
