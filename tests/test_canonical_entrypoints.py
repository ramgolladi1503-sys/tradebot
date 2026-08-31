import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_pipeline_entrypoint_is_directly_invokable():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_read_only_live_pipeline.py"), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "Permanent operator entrypoint" in result.stdout


def test_independent_validator_entrypoint_is_directly_invokable():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_read_only_live_pipeline.py"), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "Validate one session" in result.stdout
