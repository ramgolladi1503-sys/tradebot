from pathlib import Path

from core import kite_depth_ws


def test_kite_depth_ws_wires_handshake_proof_events():
    source = Path("core/kite_depth_ws.py").read_text()

    assert "build_ws_handshake_attempt_event" in source
    assert "build_ws_auth_failure_proof_event" in source
    assert "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF" in source
    assert "FEED_WS_AUTH_FAILURE_PROOF" in source
    assert "public_key=api_key" in source
    assert "access_token=access_token" in source


def test_kite_depth_ws_does_not_log_full_access_token_in_proof_logger():
    source = Path("core/kite_depth_ws.py").read_text()

    marker = "feed_ws_handshake_credential_proof"
    assert marker in source

    proof_block = source[source.index(marker): source.index(marker) + 800]
    assert 'access_token_tail4' in proof_block
    assert 'access_token_len' in proof_block
    assert 'access_token_has_internal_whitespace' in proof_block
    assert 'access_token=%s' not in proof_block


def test_kite_ws_created_log_excludes_credential_fragments(caplog):
    api_key = "api-key-secret-fragment"
    access_token = "access-token-secret-fragment"

    with caplog.at_level("INFO", logger=kite_depth_ws.logger.name):
        kite_depth_ws._log_kite_ws_created(
            ticker=object(),
            api_key=api_key,
            access_token=access_token,
        )

    created_records = [record.getMessage() for record in caplog.records if "kite_ws_created" in record.getMessage()]
    assert len(created_records) == 1
    message = created_records[0]
    assert "api_key_present=True" in message
    assert "access_token_present=True" in message
    assert api_key not in message
    assert access_token not in message
    assert api_key[-4:] not in message
    assert access_token[-4:] not in message
