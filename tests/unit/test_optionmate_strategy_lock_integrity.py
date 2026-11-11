import hashlib
from pathlib import Path

FROZEN_HASHES = {
    "strategies/optionmate_rbfn_strategy.py": "352f05b011d069d2e1fb7ecfa7e4983ba607fce686d6d60303a8437814d185bf",
    "core/sentinel_live_stream_advisor.py": "6b82cf10ea5d29da88be0ca40d957a7636e33c19cb451dcc469588e36209f540",
    "core/sentinel_automated_order_dispatcher.py": "aca746d82d5ea46b96ca2bd37dbd85f850462dc224ff10fde4bedc5d6d6c0d61",
    "core/sentinel_option_strike_resolver.py": "aa7bbd2e3d5d0c13d9407a69959eed70670dda35dab47571e31e284dcd78881f",
}

def test_frozen_strategy_hashes_unmodified():
    """CI / Pytest guard enforcing that frozen strategy files cannot be altered."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    for rel_path, expected_hash in FROZEN_HASHES.items():
        file_path = base_dir / rel_path
        assert file_path.exists(), f"Strategy file missing: {rel_path}"
        current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert current_hash == expected_hash, (
            f"STRATEGY INTEGRITY BREACH: {rel_path} has been modified! "
            f"Expected {expected_hash}, got {current_hash}. "
            f"Strategy is in FROZEN_IMMUTABLE state."
        )
