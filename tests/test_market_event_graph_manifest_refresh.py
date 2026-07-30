import hashlib

import pytest

from scripts.refresh_market_event_graph_nifty50_manifest import (
    build_manifest,
    parse_constituent_csv,
    write_manifest_atomic,
)


def _csv(symbols):
    lines = ["Company Name,Industry,Symbol,Series,ISIN Code"]
    lines.extend(
        f"Company {index},Industry,{symbol},EQ,INE{index:09d}"
        for index, symbol in enumerate(symbols)
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_refresh_builds_exact_current_reference_manifest(tmp_path):
    symbols = [f"SYM{index:02d}" for index in range(50)]
    raw = _csv(symbols)

    manifest = build_manifest(
        raw,
        effective_from="2026-06-05",
        retrieved_on="2026-07-30",
        source_url="https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    )
    target = write_manifest_atomic(tmp_path / "manifest.json", manifest)

    assert manifest["constituents"] == symbols
    assert manifest["source_file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["historical_backfill_allowed"] is False
    assert manifest["manifest_status"] == (
        "CURRENT_REFERENCE_SNAPSHOT_REQUIRES_PERIODIC_OFFICIAL_REFRESH"
    )
    assert target.read_text(encoding="utf-8").endswith("\n")
    assert not (tmp_path / "manifest.json.tmp").exists()


def test_refresh_rejects_duplicate_or_non_eq_membership():
    symbols = [f"SYM{index:02d}" for index in range(49)] + ["SYM00"]

    with pytest.raises(
        ValueError,
        match="constituent_csv_requires_exactly_50_unique_eq_symbols",
    ):
        parse_constituent_csv(_csv(symbols))

    non_eq = _csv([f"SYM{index:02d}" for index in range(50)]).replace(
        b",SYM49,EQ,",
        b",SYM49,BE,",
    )
    with pytest.raises(
        ValueError,
        match="constituent_csv_requires_exactly_50_unique_eq_symbols",
    ):
        parse_constituent_csv(non_eq)
