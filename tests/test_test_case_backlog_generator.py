from __future__ import annotations

from pathlib import Path

import pandas as pd

from testing.generate_pytest_skeletons import generate


def test_catalog_generator_writes_markdown_not_pytest_placeholders(tmp_path):
    csv_path = tmp_path / "cases.csv"
    out_dir = tmp_path / "backlog"
    pd.DataFrame(
        [
            {
                "id": "AUTH-F-001",
                "category": "Authentication",
                "test_type": "Functional",
                "title": "Valid token",
                "input": "Verified profile",
                "expected": "Authenticated identity",
                "priority": "P0",
            },
            {
                "id": "AUTH-N-001",
                "category": "Authentication",
                "test_type": "Negative",
                "title": "Expired token",
                "input": "TokenException",
                "expected": "AUTH_REQUIRED",
                "priority": "P0",
            },
        ]
    ).to_csv(csv_path, index=False)

    written = generate(overwrite=True, csv_path=csv_path, out_dir=out_dir)

    assert written == [out_dir / "authentication.md"]
    text = written[0].read_text(encoding="utf-8")
    assert "AUTH-F-001" in text
    assert "AUTH-N-001" in text
    assert "not automated evidence" in text
    assert "pytest.mark.skip" not in text
    assert "assert True" not in text
    assert list(out_dir.glob("*.py")) == []


def test_catalog_generator_does_not_overwrite_without_explicit_permission(tmp_path):
    csv_path = tmp_path / "cases.csv"
    out_dir = tmp_path / "backlog"
    frame = pd.DataFrame(
        [
            {
                "id": "MD-F-001",
                "category": "Market data",
                "test_type": "Functional",
                "title": "Fresh tick",
                "input": "Tick",
                "expected": "Accepted",
                "priority": "P0",
            }
        ]
    )
    frame.to_csv(csv_path, index=False)
    first = generate(overwrite=True, csv_path=csv_path, out_dir=out_dir)[0]
    first.write_text("reviewed backlog\n", encoding="utf-8")

    written = generate(overwrite=False, csv_path=csv_path, out_dir=out_dir)

    assert written == []
    assert first.read_text(encoding="utf-8") == "reviewed backlog\n"
