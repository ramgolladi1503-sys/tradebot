from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION
from .dataset import semantic_dataset_hash, validate_candidate_dataset


HOLDOUT_ACKNOWLEDGEMENT = "OPEN_CANDIDATE_ML_V2_LOCKED_HOLDOUT"


@dataclass(frozen=True)
class LockedHoldoutSeal:
    schema_version: str
    holdout_path: str
    sidecar_path: str
    holdout_sha256: str
    semantic_sha256: str
    rows: int
    sessions: int
    first_session: str
    last_session: str
    acknowledgement_imported: bool = False
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seal_locked_holdout(
    df: pd.DataFrame,
    *,
    holdout_path: str | Path,
    holdout_fraction: float = 0.20,
) -> tuple[pd.DataFrame, LockedHoldoutSeal]:
    validate_candidate_dataset(df)
    if not 0.10 <= float(holdout_fraction) <= 0.40:
        raise ValueError("holdout_fraction_out_of_range")
    sessions = list(dict.fromkeys(df["session_date"].astype(str).tolist()))
    if len(sessions) < 10:
        raise ValueError("insufficient_sessions_for_locked_holdout")
    holdout_session_count = max(2, int(math.ceil(len(sessions) * float(holdout_fraction))))
    research_sessions = set(sessions[:-holdout_session_count])
    holdout_sessions = set(sessions[-holdout_session_count:])
    research = df[df["session_date"].astype(str).isin(research_sessions)].copy().reset_index(drop=True)
    holdout = df[df["session_date"].astype(str).isin(holdout_sessions)].copy().reset_index(drop=True)
    if research.empty or holdout.empty:
        raise ValueError("locked_holdout_partition_empty")
    if set(research["session_date"].astype(str)).intersection(set(holdout["session_date"].astype(str))):
        raise ValueError("locked_holdout_session_overlap")

    out = Path(holdout_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    holdout.to_parquet(out, index=False)
    physical_sha = _file_sha256(out)
    sidecar = out.with_suffix(out.suffix + ".sha256.json")
    sidecar_payload = {
        "schema_version": SCHEMA_VERSION,
        "path": str(out),
        "sha256": physical_sha,
        "semantic_sha256": semantic_dataset_hash(holdout),
        "rows": int(len(holdout)),
        "sessions": int(holdout["session_date"].nunique()),
        "first_session": str(holdout["session_date"].astype(str).min()),
        "last_session": str(holdout["session_date"].astype(str).max()),
        "acknowledgement_imported": False,
        **SAFETY_CONTRACT,
    }
    sidecar.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    seal = LockedHoldoutSeal(
        schema_version=SCHEMA_VERSION,
        holdout_path=str(out),
        sidecar_path=str(sidecar),
        holdout_sha256=physical_sha,
        semantic_sha256=str(sidecar_payload["semantic_sha256"]),
        rows=int(sidecar_payload["rows"]),
        sessions=int(sidecar_payload["sessions"]),
        first_session=str(sidecar_payload["first_session"]),
        last_session=str(sidecar_payload["last_session"]),
    )
    return research, seal


def verify_locked_holdout(seal: LockedHoldoutSeal) -> None:
    path = Path(seal.holdout_path)
    sidecar = Path(seal.sidecar_path)
    if not path.exists() or not sidecar.exists():
        raise FileNotFoundError("locked_holdout_artifact_missing")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if _file_sha256(path) != seal.holdout_sha256 or payload.get("sha256") != seal.holdout_sha256:
        raise ValueError("locked_holdout_physical_hash_mismatch")
    if payload.get("semantic_sha256") != seal.semantic_sha256:
        raise ValueError("locked_holdout_semantic_hash_mismatch")
    if payload.get("acknowledgement_imported") is not False:
        raise ValueError("locked_holdout_sidecar_claims_opened")
    if payload.get("allowed_for_live_execution") is not False:
        raise ValueError("locked_holdout_unsafe_authority")


def open_locked_holdout(
    seal: LockedHoldoutSeal,
    *,
    acknowledgement: str,
) -> pd.DataFrame:
    if acknowledgement != HOLDOUT_ACKNOWLEDGEMENT:
        raise PermissionError("locked_holdout_acknowledgement_invalid")
    verify_locked_holdout(seal)
    frame = pd.read_parquet(Path(seal.holdout_path))
    validate_candidate_dataset(frame)
    if semantic_dataset_hash(frame) != seal.semantic_sha256:
        raise ValueError("locked_holdout_content_changed")
    return frame
