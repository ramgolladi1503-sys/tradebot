import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "testing" / "TEST_CASES.csv"
OUT_DIR = ROOT / "testing" / "tests" / "generated"

def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")

def generate(overwrite: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(CSV_PATH)
    # Group by category for readable files
    for category, g in df.groupby("category"):
        file_name = f"test_{_slug(category)}.py"
        out_path = OUT_DIR / file_name
        if out_path.exists() and not overwrite:
            continue
        lines = []
        lines.append("import pytest")
        lines.append("")
        lines.append(f"# Auto-generated skeletons for: {category}")
        lines.append("")
        for _, row in g.iterrows():
            test_id = str(row.get("id", ""))
            title = str(row.get("title", "")).strip()
            input_desc = str(row.get("input", "")).strip()
            expected = str(row.get("expected", "")).strip()
            fn = _slug(f"{test_id}_{title}") or f"test_{_slug(test_id)}"
            lines.append("@pytest.mark.skip(reason='skeleton from TEST_CASES.csv')")
            lines.append(f"def test_{fn}():")
            lines.append(
                f"    \"\"\"{test_id} | {title}\\n\\nInput: {input_desc}\\nExpected: {expected}\\n\"\"\""
            )
            lines.append("    assert True")
            lines.append("")
        out_path.write_text("\n".join(lines))

if __name__ == "__main__":
    generate(overwrite=True)
