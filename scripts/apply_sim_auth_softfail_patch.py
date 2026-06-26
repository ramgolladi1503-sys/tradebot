from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KITE_CLIENT = ROOT / "core" / "kite_client.py"


def patch_kite_client() -> None:
    text = KITE_CLIENT.read_text()

    helper_anchor = "\n\nclass KiteClient:\n"
    helper_block = """

def _execution_mode_is_nonlive() -> bool:
    mode = str(getattr(cfg, 'EXECUTION_MODE', 'SIM') or 'SIM').strip().upper()
    return mode in {'SIM', 'PAPER', 'OFFLINE', 'BACKTEST'}


def _soften_kite_auth_failure(caller: str | None = None) -> bool:
    _ = caller
    return _execution_mode_is_nonlive()
"""
    if "def _execution_mode_is_nonlive()" not in text:
        if helper_anchor not in text:
            raise RuntimeError("Expected KiteClient class anchor not found")
        text = text.replace(helper_anchor, helper_block + helper_anchor, 1)

    old = """            if self._is_historical_auth_error(e):
                self._log_atomic(
                    \"FATAL: Kite authentication failed - stopping system. \"
                    f\"caller={_caller} symbol={_symbol} exchange={_exchange} token={instrument_token} \"
                    f\"interval={interval} reason={repr(e)}\"
                )
                raise RuntimeError(\"Kite auth failed\") from e
"""
    if old not in text:
        old = """            if self._is_historical_auth_error(e):
                self._log_atomic(
                    \"FATAL: Kite authentication failed — stopping system. \"
                    f\"caller={_caller} symbol={_symbol} exchange={_exchange} token={instrument_token} \"
                    f\"interval={interval} reason={repr(e)}\"
                )
                raise RuntimeError(\"Kite auth failed\") from e
"""
    new = """            if self._is_historical_auth_error(e):
                if _soften_kite_auth_failure(_caller):
                    self._log_atomic(
                        '[HIST_AUTH_SOFTFAIL] '
                        f\"mode={str(getattr(cfg, 'EXECUTION_MODE', 'SIM')).upper()} caller={_caller} \"
                        f\"symbol={_symbol} exchange={_exchange} token={instrument_token} interval={interval} reason={repr(e)}\"
                    )
                    return []
                self._log_atomic(
                    \"FATAL: Kite authentication failed - stopping system. \"
                    f\"caller={_caller} symbol={_symbol} exchange={_exchange} token={instrument_token} \"
                    f\"interval={interval} reason={repr(e)}\"
                )
                raise RuntimeError(\"Kite auth failed\") from e
"""
    if "[HIST_AUTH_SOFTFAIL]" not in text:
        if old not in text:
            raise RuntimeError("Expected historical auth failure block not found")
        text = text.replace(old, new, 1)

    KITE_CLIENT.write_text(text)


if __name__ == "__main__":
    patch_kite_client()
    print("Patched core/kite_client.py to soften Kite auth failures in nonlive modes")
