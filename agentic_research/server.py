from pathlib import Path

from agentic_research.api import create_app

app = create_app(Path(__file__).resolve().parents[1])
