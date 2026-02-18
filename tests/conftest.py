import sys
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep runtime writes outside the repo during tests.
os.environ.setdefault("DATA_ROOT", str(Path(tempfile.gettempdir()) / "trading_bot_runtime_tests"))
