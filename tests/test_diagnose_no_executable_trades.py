from pathlib import Path

from scripts.diagnose_no_executable_trades import diagnose


def test_diagnose_detects_common_no_executable_causes(tmp_path: Path):
    log_file = tmp_path / "live.log"
    log_file.write_text(
        "\n".join(
            [
                "2026-04-25 TB_RANKED_COUNT_EXECUTABLE {'symbol': 'NIFTY', 'count': 0}",
                "2026-04-25 CONTRACT_RESOLUTION_FAILED unresolved_contract symbol=NIFTY",
                "2026-04-25 candidate_status='blocked' readiness='ADVISORY_ONLY' execution_status='BLOCK' primary_blocker='stale_quote' quote_age_sec=4.2 spread_pct=0.7 tradingsymbol=None instrument_token=None",
                "2026-04-25 FINAL EMIT: 1091.15 non_executable QUEUE_ONLY",
            ]
        ),
        encoding="utf-8",
    )

    result = diagnose([log_file])

    assert "contract_resolution_failure" in result["likely_causes"]
    assert "stale_quote_age" in result["likely_causes"]
    assert "gating_or_approval_block" in result["likely_causes"]
    assert "ranker_produced_zero_executable" in result["likely_causes"]
    assert "missing_contract_identity" in result["likely_causes"]
    assert result["zero_executable_symbols"] == ["NIFTY"]
    assert result["field_values"]["primary_blocker"]["stale_quote"] == 1
    assert result["summary"]["final_emit"] == 1


def test_diagnose_handles_empty_or_missing_logs(tmp_path: Path):
    missing = tmp_path / "missing.log"

    result = diagnose([missing])

    assert result["likely_causes"] == []
    assert result["zero_executable_symbols"] == []
    assert result["final_emits"] == []
