from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"replace_once path={path} count={count} old={old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


def patch_opportunity_engine() -> None:
    old = '''    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        execution_allowed = False
        if isinstance(candidate, dict):
            candidate["execution_allowed"] = False
            candidate["mode"] = "advisory_only"
        elif hasattr(candidate, "execution_allowed"):
            setattr(candidate, "execution_allowed", False)
            setattr(candidate, "mode", "advisory_only")
'''
    new = '''    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        # Truth evaluation is pure: Trade is frozen and must never be mutated.
        execution_allowed = False
'''
    replace_once("core/opportunity_engine.py", old, new)
    replace_once("core/opportunity_engine.py", old, new)
    replace_once(
        "core/opportunity_engine.py",
        '''                if isinstance(candidate, dict):
                    candidate["tradable_reasons_blocking"] = list(new_blockers)
                else:
                    setattr(candidate, "tradable_reasons_blocking", list(new_blockers))
                return "NEAR_EXECUTABLE"
''',
        '''                metrics["ml_acceptance_blocker"] = "ml_probability_too_low"
                metrics["ml_tradable_reasons_blocking"] = list(new_blockers)
                return "NEAR_EXECUTABLE"
''',
    )
    test = "tests/qa/test_whole_tradebot_cross_module_truth.py"
    replace_once(test, "from copy import deepcopy\nfrom datetime import datetime\n", "from copy import deepcopy\nfrom dataclasses import asdict\nfrom datetime import datetime\n")
    replace_once(test, "[item.to_dict() for item in original]", "[asdict(item) for item in original]")
    replace_once(test, "[item.to_dict() for item in first] == [item.to_dict() for item in second]", "[asdict(item) for item in first] == [asdict(item) for item in second]")
    replace_once(test, "[item.to_dict() for item in original] == frozen_before", "[asdict(item) for item in original] == frozen_before")


def patch_archive() -> None:
    path = "core/evidence_replay_report.py"
    replace_once(path, "import json\nimport tarfile\nimport tempfile\n", "import json\nimport os\nimport shutil\nimport tarfile\nimport tempfile\n")
    marker = "\n\n@contextmanager\ndef _evidence_root(source: str | Path) -> Iterator[Path]:\n"
    helper = '''

_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


def _safe_extract_tar(archive: tarfile.TarFile, root: Path) -> None:
    root_resolved = root.resolve()
    members = archive.getmembers()
    if len(members) > _MAX_ARCHIVE_MEMBERS:
        raise ValueError("evidence_archive_member_limit_exceeded")
    total_size = 0
    validated: list[tuple[tarfile.TarInfo, Path]] = []
    for member in members:
        if member.issym() or member.islnk():
            raise ValueError(f"evidence_archive_link_rejected:{member.name}")
        if not (member.isdir() or member.isfile()):
            raise ValueError(f"evidence_archive_special_member_rejected:{member.name}")
        if member.size < 0:
            raise ValueError(f"evidence_archive_negative_size:{member.name}")
        total_size += int(member.size)
        if total_size > _MAX_ARCHIVE_BYTES:
            raise ValueError("evidence_archive_size_limit_exceeded")
        target = (root_resolved / member.name).resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError(f"evidence_archive_path_traversal:{member.name}") from exc
        validated.append((member, target))
    for member, target in validated:
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(target, 0o700)
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"evidence_archive_member_unreadable:{member.name}")
        with source, target.open("xb") as handle:
            shutil.copyfileobj(source, handle)
        os.chmod(target, 0o600)


@contextmanager
def _evidence_root(source: str | Path) -> Iterator[Path]:
'''
    replace_once(path, marker, helper)
    replace_once(path, '''            with tarfile.open(path, "r:*") as archive:
                archive.extractall(root)
            yield root
''', '''            with tarfile.open(path, "r:*") as archive:
                _safe_extract_tar(archive, root)
            yield root
''')


def patch_xml_permissions_urls() -> None:
    replace_once("core/news_ingestor.py", "import xml.etree.ElementTree as ET\n", "from defusedxml import ElementTree as ET\n")
    replace_once("core/db_guard.py", "        os.chmod(parent, 0o775)\n", "        os.chmod(parent, 0o700)\n")
    replace_once("core/db_guard.py", "        os.chmod(db_path, 0o664)\n", "        os.chmod(db_path, 0o600)\n")
    req = ROOT / "requirements.txt"
    lines = req.read_text(encoding="utf-8").splitlines()
    if "defusedxml==0.7.1" not in lines:
        lines.insert(lines.index("requests") + 1, "defusedxml==0.7.1")
        req.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write("core/intelligence/fetchers/http_fetcher.py", '''from __future__ import annotations

import ipaddress
import urllib.request
from typing import Any, Dict
from urllib.parse import urlsplit

from core.intelligence.config import config
from core.intelligence.fetchers.base import BaseFetcher

_ALLOWED_SCHEMES = {"http", "https"}


def _validate_http_url(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError("unsupported_url_scheme")
    if not parsed.hostname:
        raise ValueError("url_hostname_missing")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("url_credentials_rejected")
    hostname = parsed.hostname.strip().lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise ValueError("local_url_rejected")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified):
        raise ValueError("non_public_ip_rejected")
    return parsed.geturl()


class HTTPFetcher(BaseFetcher):
    """HTTP fetcher with explicit URL, redirect and response-size boundaries."""

    def _execute_fetch(self, url: str) -> Dict[str, Any]:
        validated_url = _validate_http_url(url)
        req = urllib.request.Request(validated_url, headers={"User-Agent": self.robots_gate.user_agent})
        with urllib.request.urlopen(req, timeout=config.fetcher.TIMEOUT_SECONDS) as response:  # nosec B310 - URL validated above
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
''')
    gemini = "core/ai_certification/gemini_client.py"
    replace_once(gemini, "import urllib.request\nfrom dataclasses import dataclass\n", "import urllib.request\nfrom dataclasses import dataclass\nfrom urllib.parse import urlsplit\n")
    replace_once(gemini, '''def _default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Google endpoint
        return response.read()
''', '''_GEMINI_API_HOST = "generativelanguage.googleapis.com"


def _validate_google_request(request: urllib.request.Request) -> None:
    parsed = urlsplit(request.full_url)
    if parsed.scheme.lower() != "https":
        raise GeminiClientError("Gemini endpoint must use HTTPS")
    if parsed.hostname != _GEMINI_API_HOST:
        raise GeminiClientError("Gemini endpoint host is not allowed")
    if parsed.username is not None or parsed.password is not None:
        raise GeminiClientError("Gemini endpoint credentials are not allowed")
    if parsed.port not in (None, 443):
        raise GeminiClientError("Gemini endpoint port is not allowed")


def _default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    _validate_google_request(request)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - exact HTTPS host validated above
        return response.read()
''')


def patch_reject_shadow() -> None:
    path = "core/reject_shadow.py"
    replace_once(path, "import logging\nfrom pathlib import Path\nimport sqlite3\n", "import logging\nimport os\nfrom pathlib import Path\nimport sqlite3\nimport tempfile\n")
    replace_once(path, '''def _fallback_db_path(desk: str) -> Path:
    return Path("/tmp/tradebot_shadow") / f"{desk}.sqlite"
''', '''def _fallback_db_path(desk: str) -> Path:
    safe_desk = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(desk)) or "DEFAULT"
    uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
    return Path(tempfile.gettempdir()) / f"tradebot_shadow_{uid}" / f"{safe_desk}.sqlite"
''')
    replace_once(path, '''        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA journal_mode=WAL")
''', '''        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path.parent, 0o700)
            conn = sqlite3.connect(path)
            os.chmod(path, 0o600)
            conn.execute("PRAGMA journal_mode=WAL")
''')


def patch_hashes_and_wheel() -> None:
    replacements = [
        ("core/analytics/schema.py", 'hashlib.sha1(payload.encode("utf-8")).hexdigest()', 'hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()'),
        ("core/candidate_journal.py", 'hashlib.sha1(json.dumps(fingerprint, sort_keys=True, default=str).encode("utf-8")).hexdigest()', 'hashlib.sha1(json.dumps(fingerprint, sort_keys=True, default=str).encode("utf-8"), usedforsecurity=False).hexdigest()'),
        ("core/expectancy/edge_ranking.py", 'sha1(canonical.encode("utf-8")).hexdigest()', 'sha1(canonical.encode("utf-8"), usedforsecurity=False).hexdigest()'),
        ("core/expectancy/setup_fingerprint.py", '            ).encode("utf-8")\n        ).hexdigest()[:16]', '            ).encode("utf-8"),\n            usedforsecurity=False,\n        ).hexdigest()[:16]'),
        ("core/intelligence/extractors/hardened_base.py", "hashlib.md5(raw_content.encode('utf-8')).hexdigest()", "hashlib.md5(raw_content.encode('utf-8'), usedforsecurity=False).hexdigest()"),
        ("core/trade_identity.py", 'hashlib.sha1(raw.encode("utf-8")).hexdigest()', 'hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()'),
        ("dashboard/ui/components.py", "h = hashlib.md5()", "h = hashlib.md5(usedforsecurity=False)"),
        ("dashboard/ui/table_model.py", 'hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()', 'hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()'),
    ]
    for path, old, new in replacements:
        replace_once(path, old, new)
    replace_once("scripts/build_secure_kiteconnect_wheel.py", 'UPSTREAM_WHEEL_SHA256 = "8670ca79428cc46fbce2b02dc59de4ba2c4ca68b40820b179836389cfa538e19"', 'UPSTREAM_WHEEL_SHA256 = "4601a48355aeeae4ac8857d44f292aef3847351840e0c18aa8f5d3c5afcf92a7"')


def add_tests() -> None:
    write("tests/qa/test_whole_tradebot_security_boundaries.py", '''from __future__ import annotations

import io
import os
import stat
import tarfile
import urllib.request
from pathlib import Path

import pytest

from core.ai_certification.gemini_client import GeminiClientError, _validate_google_request
from core.db_guard import _ensure_permissions
from core.evidence_replay_report import _evidence_root
from core.intelligence.fetchers.http_fetcher import _validate_http_url
from core.news_ingestor import _parse_rss
from core.reject_shadow import _connect_db, _fallback_db_path

pytestmark = [pytest.mark.safety, pytest.mark.chaos, pytest.mark.regression]


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_evidence_archive_rejects_path_traversal(tmp_path):
    archive_path = tmp_path / "malicious.tar"
    payload = b"escape"
    with tarfile.open(archive_path, "w") as archive:
        member = tarfile.TarInfo("../../escape.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    with pytest.raises(ValueError, match="path_traversal"):
        with _evidence_root(archive_path):
            pass
    assert not (tmp_path.parent / "escape.txt").exists()


def test_evidence_archive_rejects_links(tmp_path):
    archive_path = tmp_path / "link.tar"
    with tarfile.open(archive_path, "w") as archive:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc/passwd"
        archive.addfile(member)
    with pytest.raises(ValueError, match="link_rejected"):
        with _evidence_root(archive_path):
            pass


def test_evidence_archive_extracts_private_regular_files(tmp_path):
    archive_path = tmp_path / "valid.tar"
    payload = b"{}"
    with tarfile.open(archive_path, "w") as archive:
        member = tarfile.TarInfo("snapshot/runtime_latest/feed_runtime_latest.json")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    with _evidence_root(archive_path) as root:
        extracted = root / "snapshot/runtime_latest/feed_runtime_latest.json"
        assert extracted.read_bytes() == payload
        if os.name == "posix":
            assert _mode(extracted) == 0o600
            assert _mode(extracted.parent) == 0o700


def test_rss_parser_rejects_entity_expansion():
    malicious = """<?xml version='1.0'?><!DOCTYPE rss [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><rss><channel><item><title>&xxe;</title></item></channel></rss>"""
    assert _parse_rss(malicious, "malicious.test") == []


def test_database_permissions_are_owner_only(tmp_path):
    db_path = tmp_path / "runtime" / "tradebot.sqlite"
    _ensure_permissions(db_path)
    if os.name == "posix":
        assert _mode(db_path.parent) == 0o700
        assert _mode(db_path) == 0o600


@pytest.mark.parametrize("url", ["file:///etc/passwd", "data:text/plain,secret", "https://u:p@example.com/feed", "http://127.0.0.1/admin", "http://169.254.169.254/latest/meta-data", "http://localhost/admin"])
def test_http_fetcher_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        _validate_http_url(url)


def test_http_fetcher_accepts_public_urls():
    assert _validate_http_url("https://example.com/feed") == "https://example.com/feed"
    assert _validate_http_url("http://example.com/feed") == "http://example.com/feed"


def test_gemini_transport_restricts_endpoint():
    with pytest.raises(GeminiClientError):
        _validate_google_request(urllib.request.Request("http://generativelanguage.googleapis.com/v1beta/models/x"))
    with pytest.raises(GeminiClientError):
        _validate_google_request(urllib.request.Request("https://evil.example/v1beta/models/x"))
    _validate_google_request(urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/x"))


def test_reject_shadow_fallback_is_user_scoped_and_private(tmp_path, monkeypatch):
    import core.reject_shadow as reject_shadow
    monkeypatch.setattr(reject_shadow.tempfile, "gettempdir", lambda: str(tmp_path))
    blocked = tmp_path / "primary-is-a-file"
    blocked.write_text("blocked", encoding="utf-8")
    monkeypatch.setattr(reject_shadow, "_primary_db_path", lambda desk: blocked / "tradebot.sqlite")
    path = _fallback_db_path("desk/../../unsafe")
    assert path.parent.parent == tmp_path
    assert ".." not in path.name and "/" not in path.name
    conn, actual_path, warning = _connect_db("desk/../../unsafe")
    conn.close()
    assert actual_path == path
    assert warning == "primary_db_readonly_or_unwritable"
    if os.name == "posix":
        assert _mode(path.parent) == 0o700
        assert _mode(path) == 0o600
''')


def main() -> None:
    patch_opportunity_engine()
    patch_archive()
    patch_xml_permissions_urls()
    patch_reject_shadow()
    patch_hashes_and_wheel()
    add_tests()
    print("whole_tradebot_repairs_v1_applied")


if __name__ == "__main__":
    main()
