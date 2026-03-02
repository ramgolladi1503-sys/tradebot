import sys
import os
import tempfile
from pathlib import Path
import pytest

from core.runtime_lifecycle import lifecycle

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep runtime writes outside the repo during tests.
os.environ.setdefault("DATA_ROOT", str(Path(tempfile.gettempdir()) / "trading_bot_runtime_tests"))


@pytest.fixture(scope="session", autouse=True)
def _shutdown_managed_runtime_lifecycle():
    try:
        yield
    finally:
        lifecycle.stop_all(timeout=3.0)
