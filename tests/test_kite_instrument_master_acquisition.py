import json

from scripts import acquire_kite_instrument_master_v1 as acquire


def _kite_rows():
    return [
        {
            "instrument_token": 256265,
            "exchange_token": "1001",
            "tradingsymbol": "NIFTY 50",
            "name": "NIFTY 50",
            "exchange": "NSE",
            "segment": "NSE",
            "instrument_type": "INDEX",
        },
        {
            "instrument_token": 738561,
            "exchange_token": "2885",
            "tradingsymbol": "RELIANCE",
            "name": "RELIANCE INDUSTRIES",
            "exchange": "NSE",
            "segment": "NSE",
            "instrument_type": "EQ",
        },
    ]


def test_local_file_acquisition_preserves_raw_master_and_sidecar(tmp_path, capsys):
    source = tmp_path / "kite.json"
    source.write_text(json.dumps(_kite_rows()), encoding="utf-8")
    out_dir = tmp_path / "out"

    import sys

    old_argv = sys.argv
    try:
        sys.argv = ["acquire", "--kite-instruments-file", str(source), "--output-dir", str(out_dir)]
        assert acquire.main() == 0
    finally:
        sys.argv = old_argv
    payload = json.loads(capsys.readouterr().out)
    raw_path = out_dir / f"kite_nse_instruments_{payload['raw_sha256'][:16]}.json"
    sidecar_path = raw_path.with_suffix(".sidecar.json")

    assert raw_path.exists()
    assert json.loads(raw_path.read_text(encoding="utf-8")) == _kite_rows()
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["provider"] == "kite"
    assert sidecar["token_domain"] == "kite_instrument_token"
    assert sidecar["auth_authority_used"]["secret_values_recorded"] is False
    assert sidecar["broker_api_called"] is False


def test_acquisition_source_uses_existing_kite_client_only():
    source = (acquire.REPO_ROOT / "scripts" / "acquire_kite_instrument_master_v1.py").read_text(encoding="utf-8")

    assert "from core.kite_client import kite_client" in source
    assert "kite_client.instruments(exchange=\"NSE\", force=True)" in source
    assert "KiteConnect(" not in source
