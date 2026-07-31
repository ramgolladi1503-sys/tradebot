from __future__ import annotations

import ipaddress
import socket
import urllib.request
from typing import Any, Dict
from urllib.parse import urlsplit

from core.intelligence.config import config
from core.intelligence.fetchers.base import BaseFetcher


_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_PORTS = {"http": {None, 80}, "https": {None, 443}}


def _resolved_addresses(hostname: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        rows = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("url_hostname_resolution_failed") from exc
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for row in rows:
        raw = row[4][0]
        try:
            addresses.add(ipaddress.ip_address(raw))
        except ValueError:
            continue
    if not addresses:
        raise ValueError("url_hostname_has_no_address")
    return addresses


def _validate_http_url(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError("unsupported_url_scheme")
    if not parsed.hostname:
        raise ValueError("url_hostname_missing")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("url_credentials_rejected")
    if parsed.port not in _ALLOWED_PORTS[scheme]:
        raise ValueError("url_port_rejected")

    hostname = parsed.hostname.strip().lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise ValueError("local_url_rejected")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        addresses = _resolved_addresses(hostname)
    else:
        addresses = {literal}

    if any(not address.is_global for address in addresses):
        raise ValueError("non_public_ip_rejected")
    return parsed.geturl()


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validated = _validate_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, validated)


class HTTPFetcher(BaseFetcher):
    """Standard-library HTTP fetcher with explicit network boundaries."""

    def _execute_fetch(self, url: str) -> Dict[str, Any]:
        validated_url = _validate_http_url(url)
        request = urllib.request.Request(
            validated_url,
            headers={"User-Agent": self.robots_gate.user_agent},
        )
        opener = urllib.request.build_opener(_SafeRedirectHandler())
        with opener.open(request, timeout=config.fetcher.TIMEOUT_SECONDS) as response:  # nosec B310 - URL and redirects are validated
            final_url = _validate_http_url(response.geturl())
            content_bytes = response.read(config.fetcher.MAX_RESPONSE_SIZE_BYTES + 1)
            if len(content_bytes) > config.fetcher.MAX_RESPONSE_SIZE_BYTES:
                raise ValueError("response_size_limit_exceeded")
            return {
                "raw_content": content_bytes.decode("utf-8", errors="ignore"),
                "status": response.status,
                "url": final_url,
                "size_bytes": len(content_bytes),
                "content_type": response.headers.get("Content-Type", ""),
            }
