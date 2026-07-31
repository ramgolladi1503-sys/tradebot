from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _replace_exact(path: str, old: str, new: str, *, expected: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(
            f"repair_match_mismatch path={path} expected={expected} actual={count}"
        )
    target.write_text(text.replace(old, new), encoding="utf-8")


def _write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


def patch_opportunity_engine() -> None:
    mutation = '''    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        execution_allowed = False
        if isinstance(candidate, dict):
            candidate["execution_allowed"] = False
            candidate["mode"] = "advisory_only"
        elif hasattr(candidate, "execution_allowed"):
            setattr(candidate, "execution_allowed", False)
            setattr(candidate, "mode", "advisory_only")
'''
    pure = '''    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        # Classification is pure. Trade is frozen, and truth evaluation must
        # never mutate the candidate it inspects.
        execution_allowed = False
'''
    _replace_exact("core/opportunity_engine.py", mutation, pure, expected=2)

    ml_mutation = '''                if isinstance(candidate, dict):
                    candidate["tradable_reasons_blocking"] = list(new_blockers)
                else:
                    setattr(candidate, "tradable_reasons_blocking", list(new_blockers))
                return "NEAR_EXECUTABLE"
'''
    ml_pure = '''                metrics["ml_acceptance_blocker"] = "ml_probability_too_low"
                metrics["ml_tradable_reasons_blocking"] = list(new_blockers)
                return "NEAR_EXECUTABLE"
'''
    _replace_exact("core/opportunity_engine.py", ml_mutation, ml_pure)

    test_path = "tests/qa/test_whole_tradebot_cross_module_truth.py"
    _replace_exact(
        test_path,
        "from copy import deepcopy\nfrom datetime import datetime\n",
        "from copy import deepcopy\nfrom dataclasses import asdict\nfrom datetime import datetime\n",
    )
    _replace_exact(
        test_path,
        "[item.to_dict() for item in original]",
        "[asdict(item) for item in original]",
        expected=2,
    )
    _replace_exact(
        test_path,
        "[item.to_dict() for item in first] == [item.to_dict() for item in second]",
        "[asdict(item) for item in first] == [asdict(item) for item in second]",
    )


def patch_evidence_archive() -> None:
    path = "core/evidence_replay_report.py"
    _replace_exact(
        path,
        "import json\nimport tarfile\nimport tempfile\n",
        "import json\nimport os\nimport shutil\nimport tarfile\nimport tempfile\n",
    )
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
        os.chmod(target.parent, 0o700)
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"evidence_archive_member_unreadable:{member.name}")
        with source, target.open("xb") as handle:
            shutil.copyfileobj(source, handle)
        os.chmod(target, 0o600)


@contextmanager
def _evidence_root(source: str | Path) -> Iterator[Path]:
'''
    _replace_exact(path, marker, helper)
    _replace_exact(
        path,
        '''            with tarfile.open(path, "r:*") as archive:
                archive.extractall(root)
            yield root
''',
        '''            with tarfile.open(path, "r:*") as archive:
                _safe_extract_tar(archive, root)
            yield root
''',
    )


def patch_reject_shadow() -> None:
    path = "core/reject_shadow.py"
    _replace_exact(
        path,
        "import logging\nfrom pathlib import Path\nimport sqlite3\n",
        "import logging\nimport os\nfrom pathlib import Path\nimport sqlite3\nimport tempfile\n",
    )
    _replace_exact(
        path,
        '''def _fallback_db_path(desk: str) -> Path:
    return Path("/tmp/tradebot_shadow") / f"{desk}.sqlite"
''',
        '''def _fallback_db_path(desk: str) -> Path:
    safe_desk = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in str(desk)
    ) or "DEFAULT"
    uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
    return Path(tempfile.gettempdir()) / f"tradebot_shadow_{uid}" / f"{safe_desk}.sqlite"
''',
    )
    _replace_exact(
        path,
        '''        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA journal_mode=WAL")
''',
        '''        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path.parent, 0o700)
            conn = sqlite3.connect(path)
            if path != Path(":memory:"):
                os.chmod(path, 0o600)
            conn.execute("PRAGMA journal_mode=WAL")
''',
    )
    _replace_exact(
        path,
        "        except sqlite3.OperationalError:\n            continue\n",
        "        except (OSError, sqlite3.Error):\n            continue\n",
    )


def patch_non_security_hashes() -> None:
    replacements = (
        (
            "core/analytics/schema.py",
            'hashlib.sha1(payload.encode("utf-8")).hexdigest()',
            'hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()',
        ),
        (
            "core/candidate_journal.py",
            'hashlib.sha1(json.dumps(fingerprint, sort_keys=True, default=str).encode("utf-8")).hexdigest()',
            'hashlib.sha1(json.dumps(fingerprint, sort_keys=True, default=str).encode("utf-8"), usedforsecurity=False).hexdigest()',
        ),
        (
            "core/expectancy/edge_ranking.py",
            'sha1(canonical.encode("utf-8")).hexdigest()',
            'sha1(canonical.encode("utf-8"), usedforsecurity=False).hexdigest()',
        ),
        (
            "core/expectancy/setup_fingerprint.py",
            '            ).encode("utf-8")\n        ).hexdigest()[:16]',
            '            ).encode("utf-8"),\n            usedforsecurity=False,\n        ).hexdigest()[:16]',
        ),
        (
            "core/intelligence/extractors/hardened_base.py",
            "hashlib.md5(raw_content.encode('utf-8')).hexdigest()",
            "hashlib.md5(raw_content.encode('utf-8'), usedforsecurity=False).hexdigest()",
        ),
        (
            "core/trade_identity.py",
            'hashlib.sha1(raw.encode("utf-8")).hexdigest()',
            'hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()',
        ),
        (
            "dashboard/ui/components.py",
            "h = hashlib.md5()",
            "h = hashlib.md5(usedforsecurity=False)",
        ),
        (
            "dashboard/ui/table_model.py",
            'hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()',
            'hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()',
        ),
    )
    for path, old, new in replacements:
        _replace_exact(path, old, new)


def add_negative_controls() -> None:
    _write(
        "tests/qa/test_remaining_whole_tradebot_security.py",
        '''from __future__ import annotations

import io
import os
import stat
import tarfile

import pytest

from core.evidence_replay_report import _evidence_root
from core.reject_shadow import _connect_db, _fallback_db_path


pytestmark = [pytest.mark.safety, pytest.mark.chaos, pytest.mark.regression]


def _mode(path) -> int:
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


def test_evidence_archive_extracts_private_regular_file(tmp_path):
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


def test_reject_shadow_fallback_is_sanitized_user_scoped_and_private(tmp_path, monkeypatch):
    import core.reject_shadow as reject_shadow

    monkeypatch.setattr(reject_shadow.tempfile, "gettempdir", lambda: str(tmp_path))
    blocked_parent = tmp_path / "primary-is-a-file"
    blocked_parent.write_text("blocked", encoding="utf-8")
    monkeypatch.setattr(
        reject_shadow,
        "_primary_db_path",
        lambda desk: blocked_parent / "tradebot.sqlite",
    )

    path = _fallback_db_path("desk/../../unsafe")
    assert path.parent.parent == tmp_path
    assert ".." not in path.name
    assert "/" not in path.name

    connection, actual_path, warning = _connect_db("desk/../../unsafe")
    connection.close()
    assert actual_path == path
    assert warning == "primary_db_readonly_or_unwritable"
    if os.name == "posix":
        assert _mode(path.parent) == 0o700
        assert _mode(path) == 0o600
''',
    )


def main() -> int:
    patch_opportunity_engine()
    patch_evidence_archive()
    patch_reject_shadow()
    patch_non_security_hashes()
    add_negative_controls()
    print("remaining_whole_tradebot_repairs_built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
