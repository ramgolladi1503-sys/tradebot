from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from research.macd_futures_participation_regime_v1.analysis import CampaignBlocked

EXPECTED_SIGNAL_TRADES = 148
EXPECTED_SIGNAL_MEAN_NET_6BPS = 8.0774
MEAN_TOLERANCE_BPS = 0.0002

REQUIRED_FILES = (
    "MACD_MATCHED_PLACEBO_ASSIGNMENTS.csv",
    "MACD_SIGNAL_TRADE_PATH_DECOMPOSITION.csv",
    "MACD_MATCHED_PLACEBO_PAYOFF_LEDGER.csv",
)


@dataclass(frozen=True)
class CanonicalMacdEvidence:
    root: Path
    assignments: Path
    signal_paths: Path
    placebo_payoffs: Path
    signal_trade_count: int
    signal_mean_net_6bps: float


def _candidate_roots(volumes_root: Path) -> list[Path]:
    if not volumes_root.exists():
        raise CampaignBlocked(f"VOLUMES_ROOT_MISSING:{volumes_root}")
    return sorted(
        [
            p
            for p in volumes_root.glob(
                "macd_path_dependent_matched_placebo_mechanism_test_v*"
            )
            if p.is_dir()
        ]
    )


def _inspect(root: Path) -> CanonicalMacdEvidence | None:
    files = {name: root / name for name in REQUIRED_FILES}
    if not all(path.is_file() for path in files.values()):
        return None

    try:
        signal = pd.read_csv(files["MACD_SIGNAL_TRADE_PATH_DECOMPOSITION.csv"])
    except Exception as exc:  # pragma: no cover - surfaced as non-authoritative root
        raise CampaignBlocked(f"SIGNAL_LEDGER_READ_FAILED:{root}:{exc}") from exc

    required_signal_cols = {"trade_id", "entry_timestamp", "net_6bps"}
    if not required_signal_cols.issubset(signal.columns):
        return None
    if signal["trade_id"].astype(str).duplicated().any():
        return None

    n = int(len(signal))
    mean = float(pd.to_numeric(signal["net_6bps"], errors="coerce").mean())
    if n != EXPECTED_SIGNAL_TRADES:
        return None
    if not pd.notna(mean):
        return None
    if abs(mean - EXPECTED_SIGNAL_MEAN_NET_6BPS) > MEAN_TOLERANCE_BPS:
        return None

    return CanonicalMacdEvidence(
        root=root,
        assignments=files["MACD_MATCHED_PLACEBO_ASSIGNMENTS.csv"],
        signal_paths=files["MACD_SIGNAL_TRADE_PATH_DECOMPOSITION.csv"],
        placebo_payoffs=files["MACD_MATCHED_PLACEBO_PAYOFF_LEDGER.csv"],
        signal_trade_count=n,
        signal_mean_net_6bps=mean,
    )


def resolve_canonical_macd_evidence(volumes_root: Path) -> CanonicalMacdEvidence:
    """Resolve the canonical 148-trade matched-placebo evidence fail-closed.

    Discovery is intentionally narrow: only roots with the exact campaign prefix
    are considered, and a root must reproduce the frozen signal count and mean
    net expectancy before it is admitted. No outcome is optimized here.
    """
    roots = _candidate_roots(volumes_root)
    if not roots:
        raise CampaignBlocked("CANONICAL_MACD_ROOT_NOT_FOUND")

    admitted: list[CanonicalMacdEvidence] = []
    for root in roots:
        inspected = _inspect(root)
        if inspected is not None:
            admitted.append(inspected)

    if not admitted:
        raise CampaignBlocked("CANONICAL_MACD_ROOT_NOT_RECONCILED")
    if len(admitted) > 1:
        roots_text = ",".join(str(item.root) for item in admitted)
        raise CampaignBlocked(f"CANONICAL_MACD_ROOT_AMBIGUOUS:{roots_text}")
    return admitted[0]
