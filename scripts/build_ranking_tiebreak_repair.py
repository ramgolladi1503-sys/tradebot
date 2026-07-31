from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    path = ROOT / "core/opportunity_engine.py"
    text = path.read_text(encoding="utf-8")
    old = '''    scored.sort(
        key=lambda item: (
            -item[0][0],
            -item[0][1],
            -item[0][2],
            -item[0][3],
            -item[0][4],
            -item[0][5],
            item[0][6],
            item[0][7],
        )
    )
'''
    new = '''    scored.sort(
        key=lambda item: (
            -item[0][0],
            -item[0][1],
            -item[0][2],
            -item[0][3],
            -item[0][4],
            -item[0][5],
            -item[0][6],
            -item[0][7],
            item[0][8],
            item[0][9],
        )
    )
'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"ranking_tiebreak_match_mismatch:{count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("ranking_tiebreak_repair_built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
