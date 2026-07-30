from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "testing" / "TEST_CASES.csv"
OUT_DIR = ROOT / "testing" / "generated_case_backlog"


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def generate(
    overwrite: bool = False,
    *,
    csv_path: Path = CSV_PATH,
    out_dir: Path = OUT_DIR,
) -> list[Path]:
    """Render the structured test catalog as non-executable Markdown backlog.

    Catalog rows are requirements, not passing tests. This generator must never
    create files collected by pytest, skipped placeholders, or unconditional
    assertions. A case moves into ``tests/`` only after it has real fixtures,
    behavior assertions, and traceability to its catalog ID.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(csv_path)
    written: list[Path] = []
    for category, group in frame.groupby("category"):
        out_path = out_dir / f"{_slug(str(category))}.md"
        if out_path.exists() and not overwrite:
            continue
        lines = [
            f"# {_cell(category)} test-case backlog",
            "",
            "> These entries are requirements. They are not automated evidence until implemented under `tests/` with real assertions.",
            "",
            "| ID | Priority | Type | Title | Input | Expected |",
            "|---|---|---|---|---|---|",
        ]
        for _, row in group.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(row.get("id", "")),
                        _cell(row.get("priority", "")),
                        _cell(row.get("test_type", "")),
                        _cell(row.get("title", "")),
                        _cell(row.get("input", "")),
                        _cell(row.get("expected", "")),
                    ]
                )
                + " |"
            )
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(out_path)
    return written


if __name__ == "__main__":
    generate(overwrite=True)
