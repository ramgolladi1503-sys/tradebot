#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path


MONTH_MAP = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


def catalog_aeron7(source_root: str | Path = "data/aeron7_data") -> dict[str, object]:
    root = Path(source_root)
    dates: set[str] = set()
    year_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".csv"}:
            continue
        rel = path.relative_to(root).parts
        if len(rel) < 3:
            continue
        year, month, day_folder = rel[0], rel[1], rel[2]
        symbol_counts[path.stem.upper()] += 1
        if not (year.isdigit() and len(year) == 4):
            continue
        month_num = MONTH_MAP.get(month[:3].upper())
        day = day_folder[:2]
        if month_num is None or not day.isdigit() or len(day) != 2:
            continue
        try:
            day_key = datetime.strptime(f"{year}{month_num}{day}", "%Y%m%d").strftime("%Y%m%d")
        except Exception:
            continue
        dates.add(day_key)
        year_counts[year] += 1

    ordered_dates = sorted(dates)
    catalog = {
        "classification": "AERON7_DATA_CATALOG_READY" if ordered_dates else "AERON7_DATA_CATALOG_EMPTY",
        "dates_available": ordered_dates,
        "earliest_date": ordered_dates[0] if ordered_dates else None,
        "latest_date": ordered_dates[-1] if ordered_dates else None,
        "years_available": sorted(year_counts),
        "year_file_counts": dict(sorted(year_counts.items())),
        "top_symbols": [name for name, _ in symbol_counts.most_common(20)],
        "source_root": str(root),
    }
    return catalog


def main() -> int:
    catalog = catalog_aeron7()
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "aeron7_data_catalog.json", "w") as f:
        json.dump(catalog, f, indent=2)

    with open(out_dir / "aeron7_data_catalog.md", "w") as f:
        f.write("# Aeron7 Data Catalog\n\n")
        f.write(f"- Classification: {catalog['classification']}\n")
        f.write(f"- Dates Available: {len(catalog['dates_available'])}\n")
        f.write(f"- Earliest: {catalog['earliest_date']}\n")
        f.write(f"- Latest: {catalog['latest_date']}\n")
        f.write(f"- Years: {', '.join(catalog['years_available'])}\n")
        f.write(f"- Source Root: {catalog['source_root']}\n")

    print(f"Catalogued {len(catalog['dates_available'])} Aeron7 dates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
