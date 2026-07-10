import json
from pathlib import Path
import os

BASE_DIR = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")

def _load(name):
    path = BASE_DIR / name
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def test_ledger_audit_flags_100_percent_win_rate_with_over_20_trades():
    audit = _load("phase_4_trade_ledger_audit.json")
    if audit and audit.get("trade_count", 0) > 20 and audit.get("win_rate", 0) == 1.0:
        assert audit.get("classification") in ["TRADE_LEDGER_AUDIT_SUSPICIOUS", "TRADE_LEDGER_AUDIT_FAILED"]
        assert "SUSPICIOUS_PERFECT_WIN_RATE" in audit.get("suspicious_blockers", [])

def test_ledger_audit_flags_profit_factor_over_50():
    audit = _load("phase_4_trade_ledger_audit.json")
    if audit and audit.get("profit_factor", 0) > 50:
        assert audit.get("classification") in ["TRADE_LEDGER_AUDIT_SUSPICIOUS", "TRADE_LEDGER_AUDIT_FAILED"]
        assert "SUSPICIOUS_PROFIT_FACTOR" in audit.get("suspicious_blockers", [])

def test_ledger_audit_blocks_same_candle_entry_exit():
    audit = _load("phase_4_trade_ledger_audit.json")
    if audit and "LOOKAHEAD_OR_SAME_CANDLE_FILL_RISK" in audit.get("failed_blockers", []):
        assert audit.get("classification") == "TRADE_LEDGER_AUDIT_FAILED"
        
def test_pnl_recomputed_mismatch_fails_audit():
    audit = _load("phase_4_trade_ledger_audit.json")
    if audit and "PNL_MISMATCH" in audit.get("failed_blockers", []):
        assert audit.get("classification") == "TRADE_LEDGER_AUDIT_FAILED"

def test_rr_recomputed_mismatch_fails_audit():
    audit = _load("phase_4_trade_ledger_audit.json")
    if audit and "RR_MISMATCH" in audit.get("failed_blockers", []):
        assert audit.get("classification") == "TRADE_LEDGER_AUDIT_FAILED"

def test_phase_4_cannot_pass_if_ledger_audit_is_suspicious():
    audit = _load("phase_4_trade_ledger_audit.json")
    p4 = _load("phase_4_report.json")
    if audit and p4 and audit.get("classification") == "TRADE_LEDGER_AUDIT_SUSPICIOUS":
        assert p4.get("passed") is False
        assert "TRADE_LEDGER_AUDIT_SUSPICIOUS" in p4.get("blockers", [])

def test_phase_4_cannot_pass_if_ledger_audit_fails():
    audit = _load("phase_4_trade_ledger_audit.json")
    p4 = _load("phase_4_report.json")
    if audit and p4 and audit.get("classification") == "TRADE_LEDGER_AUDIT_FAILED":
        assert p4.get("passed") is False
        assert "TRADE_LEDGER_AUDIT_FAILED" in p4.get("blockers", [])
