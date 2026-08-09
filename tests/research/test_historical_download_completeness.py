import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "research" / "hypothesis_factory" / "audit_historical_download_completeness.py"
spec = importlib.util.spec_from_file_location("audit_historical_download_completeness", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def index_payload(nifty_dates=None, banknifty_dates=None, sensex_dates=None):
    nifty_dates = nifty_dates or []
    banknifty_dates = banknifty_dates or []
    sensex_dates = sensex_dates or []
    dates = sorted(set(nifty_dates + banknifty_dates + sensex_dates))
    return {
        "roots": ["/tmp/data"],
        "sessions": [{"date": d} for d in dates],
        "summary": {
            "files": len(dates),
            "underlying_sessions": {
                "NIFTY": nifty_dates,
                "BANKNIFTY": banknifty_dates,
                "SENSEX": sensex_dates,
            },
        },
    }


def test_partial_download_fails_closed():
    idx = index_payload(
        nifty_dates=["2024-06-04", "2024-06-10"],
        banknifty_dates=[],
        sensex_dates=["2024-06-04", "2024-06-05", "2024-06-10"],
    )
    result = mod.audit(idx, 20, {"BANKNIFTY": 20, "NIFTY": 20})
    assert result["status"] == "INCOMPLETE_DOWNLOAD"
    codes = {x["code"] for x in result["failures"]}
    assert "TOTAL_SESSION_COVERAGE_BELOW_MINIMUM" in codes
    assert "UNDERLYING_FAMILY_COVERAGE_BELOW_MINIMUM" in codes
    assert result["runtime_authority"] == "NONE"
    assert result["broker_actions_allowed"] is False


def test_complete_requested_gate_passes_without_certifying():
    dates = [f"2024-05-{d:02d}" for d in range(1, 21)]
    idx = index_payload(nifty_dates=dates, banknifty_dates=dates)
    result = mod.audit(idx, 20, {"BANKNIFTY": 20, "NIFTY": 20})
    assert result["status"] == "COMPLETE_FOR_REQUESTED_GATE"
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["runtime_authority"] == "NONE"


def test_remote_manifest_detects_missing_local_sessions():
    idx = index_payload(nifty_dates=["2024-06-04"])
    remote = {"session_dates": ["2024-06-04", "2024-06-05"]}
    result = mod.audit(idx, 1, {"NIFTY": 1}, remote)
    assert result["status"] == "INCOMPLETE_DOWNLOAD"
    assert result["missing_remote_dates"] == ["2024-06-05"]
    assert any(x["code"] == "REMOTE_SESSIONS_MISSING_LOCALLY" for x in result["failures"])
