from __future__ import annotations

from research.opening_dislocation_reversal.fresh_epoch_acquisition import (
    classify_historical_access,
    redacted_error,
    token_presence_audit,
)


def test_token_presence_audit_never_reports_secret_details():
    audit = token_presence_audit("secret-token-value")
    assert audit["token_present"] is True
    assert audit["token_printed"] is False
    assert audit["token_logged"] is False
    assert audit["token_serialized"] is False
    assert audit["token_hashed"] is False
    assert audit["token_length_reported"] is False
    assert audit["token_prefix_suffix_reported"] is False
    assert "secret-token-value" not in repr(audit)


def test_invalid_token_classification_stops_at_historical_access():
    assert classify_historical_access(401, {"status": "error"}) == "TOKEN_INVALID_OR_EXPIRED"
    assert classify_historical_access(403, {"status": "error"}) == "TOKEN_VALID_BUT_HISTORICAL_ACCESS_DENIED"


def test_historical_success_and_contract_mismatch_classification():
    assert classify_historical_access(200, {"status": "success", "data": {"candles": []}}) == (
        "TOKEN_VALID_HISTORICAL_ACCESS_CONFIRMED"
    )
    assert classify_historical_access(400, {"status": "error"}) == "ENDPOINT_CONTRACT_MISMATCH"


def test_redacted_http_errors_keep_headers_and_messages_out():
    redacted = redacted_error(400, {"errors": [{"errorCode": "UDAPI1148", "message": "too much detail"}]})
    assert redacted == {
        "status_code": 400,
        "provider_error_code": "UDAPI1148",
        "message_class": "PROVIDER_ERROR_REDACTED",
    }
    assert "too much detail" not in repr(redacted)
