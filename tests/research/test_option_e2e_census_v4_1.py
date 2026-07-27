from __future__ import annotations

import tarfile
import zipfile

import pandas as pd

from research.option_e2e_recertification_v4.data_census_v4_1.census import build_census


def test_v4_1_records_root_proof_and_parse_status(tmp_path) -> None:
    quote_path = tmp_path / "nifty_option_quotes.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-07-01T09:15:00+05:30",
                "tradingsymbol": "NIFTY2670125000CE",
                "expiry": "2026-07-30",
                "strike": 25000,
                "option_type": "CE",
                "bid": 100.0,
                "ask": 101.0,
            }
        ]
    ).to_csv(quote_path, index=False)

    files, summary, root_proofs = build_census((tmp_path,), repo_root=tmp_path)

    assert [item.logical_path for item in files] == ["nifty_option_quotes.csv"]
    assert files[0].parse_status == "parsed"
    assert files[0].parse_error == ""
    assert files[0].root == str(tmp_path)
    assert files[0].root_relative_path == "nifty_option_quotes.csv"
    assert files[0].usable_for_option_e2e is True
    assert summary.executable_quote_files == 1
    assert root_proofs[0].exists is True
    assert root_proofs[0].file_count >= 1
    assert root_proofs[0].sha256


def test_v4_1_lists_archives_without_extracting_and_skips_appledouble(tmp_path) -> None:
    archive_path = tmp_path / "candidate_replay.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("quotes/nifty_option_quotes.csv", "timestamp,bid,ask\n2026-07-01T09:15:00+05:30,1,2\n")
        archive.writestr("__MACOSX/._nifty_option_quotes.csv", "appledouble")

    files, summary, _root_proofs = build_census((tmp_path,), repo_root=tmp_path)

    assert summary.archive_files == 1
    assert summary.archive_members_scanned == 1
    assert any(item.parse_status == "archive_listed" for item in files)
    member = next(item for item in files if item.archive_member_path)
    assert member.archive_member_path == "quotes/nifty_option_quotes.csv"
    assert member.container_path.endswith("candidate_replay.zip")
    assert "MACOSX" not in member.archive_member_path


def test_v4_1_lists_tar_gz_members_without_extracting(tmp_path) -> None:
    member_source = tmp_path / "authority.csv"
    member_source.write_text("asof,tradingsymbol,expiry,strike,lot_size\n2026-07-01,NIFTY2670125000CE,2026-07-30,25000,75\n", encoding="utf-8")
    archive_path = tmp_path / "authority.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(member_source, arcname="authority.csv")
    member_source.unlink()

    files, summary, _root_proofs = build_census((tmp_path,), repo_root=tmp_path)

    assert summary.archive_files == 1
    assert summary.archive_members_scanned == 1
    member = next(item for item in files if item.archive_member_path)
    assert member.parse_status == "archive_member_listed"
    assert member.suffix == ".csv"
