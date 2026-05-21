from pathlib import Path


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
