from pathlib import Path
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def setup() -> None:
    """Ensure repo root is on sys.path for script imports."""
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


setup()
