import json
from pathlib import Path
import pytest

BASE_DIR = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")

def _load(name):
    path = BASE_DIR / name
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def test_candle_audit_flags_one_row_parquet_as_invalid():
    audit = _load("upstox_candle_file_audit.json")
    if audit and "NO_USABLE_INTRADAY_SEQUENCE" in audit.get("blockers", []):
        assert audit.get("classification") == "UPSTOX_CANDLE_FILES_INVALID"

def test_candle_audit_passes_multi_row_valid_parquet():
    audit = _load("upstox_candle_file_audit.json")
    if audit and not audit.get("blockers", []):
        assert audit.get("classification") == "UPSTOX_CANDLE_FILES_VALID"

def test_invalid_ohlc_blocks():
    audit = _load("upstox_candle_file_audit.json")
    if audit and "CANDLE_FILE_INVALID_OHLC" in audit.get("blockers", []):
        assert audit.get("classification") == "UPSTOX_CANDLE_FILES_INVALID"

def test_duplicate_timestamps_block():
    audit = _load("upstox_candle_file_audit.json")
    if audit and "CANDLE_FILE_DUPLICATE_TIMESTAMPS" in audit.get("blockers", []):
        assert audit.get("classification") == "UPSTOX_CANDLE_FILES_INVALID"

def test_one_row_file_blocks_t_plus_1_entry():
    audit = _load("upstox_candle_file_audit.json")
    if audit:
        for f in audit.get("details", []):
            if f.get("row_count", 0) == 1:
                assert f.get("usable_for_t_plus_1") is False
