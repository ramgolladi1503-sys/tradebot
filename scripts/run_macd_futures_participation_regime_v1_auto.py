from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.macd_futures_participation_regime_v1.analysis import (  # noqa: E402
    CampaignBlocked,
    sha256_file,
)
from research.macd_futures_participation_regime_v1.resolver import (  # noqa: E402
    resolve_canonical_macd_evidence,
)

EXPECTED_ALIGNED_SHA256 = (
    "2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9"
)
DEFAULT_ALIGNED = Path(
    "/Users/madhuram/tradebot/data/research/nifty_futures_alignment_v1/"
    "NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet"
)
DEFAULT_VOLUMES_ROOT = Path("/Volumes/TradeBotData")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Resolve frozen authorities and run MACD x futures regime V1"
    )
    p.add_argument("--output-root", required=True)
    p.add_argument("--aligned-parquet", default=str(DEFAULT_ALIGNED))
    p.add_argument("--volumes-root", default=str(DEFAULT_VOLUMES_ROOT))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        aligned = Path(args.aligned_parquet)
        if not aligned.is_file():
            raise CampaignBlocked(f"ALIGNED_PARQUET_MISSING:{aligned}")
        aligned_sha = sha256_file(aligned)
        if aligned_sha != EXPECTED_ALIGNED_SHA256:
            raise CampaignBlocked(
                "ALIGNED_PARQUET_SHA_MISMATCH:"
                f"expected={EXPECTED_ALIGNED_SHA256}:actual={aligned_sha}"
            )

        canonical = resolve_canonical_macd_evidence(Path(args.volumes_root))
        resolution = {
            "aligned_parquet": str(aligned),
            "aligned_sha256": aligned_sha,
            "canonical_macd_root": str(canonical.root),
            "signal_trade_count": canonical.signal_trade_count,
            "signal_mean_net_6bps": canonical.signal_mean_net_6bps,
            "resolver_status": "PASS",
        }
        (output_root / "AUTO_RESOLUTION.json").write_text(
            json.dumps(resolution, indent=2, sort_keys=True) + "\n"
        )

        runner = ROOT / "scripts/run_macd_futures_participation_regime_v1.py"
        cmd = [
            sys.executable,
            str(runner),
            "--aligned-parquet",
            str(aligned),
            "--assignments",
            str(canonical.assignments),
            "--signal-paths",
            str(canonical.signal_paths),
            "--placebo-payoffs",
            str(canonical.placebo_payoffs),
            "--output-root",
            str(output_root),
        ]
        completed = subprocess.run(cmd, cwd=ROOT, check=False)
        return int(completed.returncode)
    except CampaignBlocked as exc:
        blocked = {
            "campaign": "MACD_FUTURES_PARTICIPATION_REGIME_V1",
            "verdict": "MACD_FUTURES_REGIME_BLOCKED",
            "blocker": str(exc),
            "structural_edge_certified": False,
            "execution_viable": "UNKNOWN",
            "broker_calls": 0,
            "orders": 0,
        }
        (output_root / "AUTO_RESOLUTION.json").write_text(
            json.dumps(blocked, indent=2, sort_keys=True) + "\n"
        )
        print(json.dumps(blocked, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
