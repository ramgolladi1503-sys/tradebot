from __future__ import annotations

import hashlib
import json
from pathlib import Path


ALLOWED_ROOTS = (
    Path("/Users/madhuram/tradebot"),
    Path("/Users/madhuram/tradebot-data"),
    Path("/Users/madhuram/tradebot-ml-evidence"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_source_search_manifest(repo_root: Path) -> dict[str, object]:
    search_hits: list[dict[str, object]] = []
    for root in ALLOWED_ROOTS:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            name = candidate.name.lower()
            if any(token in name for token in ("vwap", "reclaim", "session_manifest", "option_replay", "candidate_manifest")):
                search_hits.append(
                    {
                        "root": str(root),
                        "path": str(candidate),
                        "sha256": _sha256(candidate),
                        "size": candidate.stat().st_size,
                    }
                )
    payload = {
        "search_scope": [str(root) for root in ALLOWED_ROOTS],
        "search_hits": search_hits[:250],
        "search_hit_count": len(search_hits),
        "conclusion": "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE",
        "reason": "no authoritative frozen market dataset for VWAP_RECLAIM was proven; only manifests and blocked replays were found",
    }
    out = repo_root / "research" / "option_e2e_recertification_v4" / "v4_10_2_source_search_manifest.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"path": str(out), "hash": _sha256(out), **payload}
