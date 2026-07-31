from __future__ import annotations

import os
import socket
import stat

import pytest

from core.db_guard import _ensure_permissions
from core.intelligence.fetchers import http_fetcher
from core.news_ingestor import _parse_rss


pytestmark = [pytest.mark.safety, pytest.mark.chaos, pytest.mark.regression]


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _public_dns(hostname, port, *, type):
    assert hostname == "example.com"
    assert type == socket.SOCK_STREAM
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


def _private_dns(hostname, port, *, type):
    assert type == socket.SOCK_STREAM
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]


def test_rss_parser_rejects_external_entity_payload():
    malicious = """<?xml version='1.0'?>
    <!DOCTYPE rss [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>
    <rss><channel><item><title>&xxe;</title></item></channel></rss>"""

    assert _parse_rss(malicious, "malicious.test") == []


def test_runtime_database_permissions_are_owner_only(tmp_path):
    db_path = tmp_path / "runtime" / "tradebot.sqlite"

    _ensure_permissions(db_path)

    assert db_path.exists()
    if os.name == "posix":
        assert _mode(db_path.parent) == 0o700
        assert _mode(db_path) == 0o600


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "data:text/plain,secret",
        "https://user:password@example.com/feed",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/admin",
        "https://example.com:8443/feed",
    ],
)
def test_intelligence_fetcher_rejects_unsafe_targets(monkeypatch, url):
    monkeypatch.setattr(http_fetcher.socket, "getaddrinfo", _public_dns)

    with pytest.raises(ValueError):
        http_fetcher._validate_http_url(url)


def test_intelligence_fetcher_rejects_public_name_resolving_private(monkeypatch):
    monkeypatch.setattr(http_fetcher.socket, "getaddrinfo", _private_dns)

    with pytest.raises(ValueError, match="non_public_ip_rejected"):
        http_fetcher._validate_http_url("https://example.com/feed")


def test_intelligence_fetcher_accepts_public_https(monkeypatch):
    monkeypatch.setattr(http_fetcher.socket, "getaddrinfo", _public_dns)

    assert http_fetcher._validate_http_url("https://example.com/feed") == "https://example.com/feed"


def test_redirect_handler_validates_target_before_following(monkeypatch):
    monkeypatch.setattr(http_fetcher.socket, "getaddrinfo", _private_dns)
    handler = http_fetcher._SafeRedirectHandler()

    with pytest.raises(ValueError, match="non_public_ip_rejected"):
        handler.redirect_request(
            req=None,
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="https://example.com/internal",
        )
