from __future__ import annotations

from collections.abc import Mapping, Sequence

from .contracts import Bar, Candidate, Side


HORIZONS = (15, 30, 60, "close")


def horizon_returns_bps(candidate: Candidate, bars_after_entry: Sequence[Bar]) -> dict[str, float | None]:
    if not bars_after_entry:
        return {str(h): None for h in HORIZONS}
    entry = bars_after_entry[0]
    direction = 1 if candidate.side == Side.LONG else -1
    out: dict[str, float | None] = {}
    for horizon in HORIZONS:
        if horizon == "close":
            exit_bar = bars_after_entry[-1]
        else:
            index = int(horizon) // 5
            if index >= len(bars_after_entry):
                out[f"{horizon}m"] = None
                continue
            exit_bar = bars_after_entry[index]
        value = direction * ((exit_bar.close / entry.open) - 1.0) * 10_000
        out["close" if horizon == "close" else f"{horizon}m"] = value
    return out


def summarize(values: Sequence[float | None], *, cost_bps: float = 5.0) -> Mapping[str, float | int | str]:
    observed = [float(value) for value in values if value is not None]
    if not observed:
        return {"count": 0, "mean_gross_bps": 0.0, "mean_net_bps": 0.0, "win_rate": 0.0, "verdict": "INSUFFICIENT_DATA"}
    wins = sum(1 for value in observed if value > 0)
    mean = sum(observed) / len(observed)
    return {
        "count": len(observed),
        "mean_gross_bps": mean,
        "mean_net_bps": mean - cost_bps,
        "win_rate": wins / len(observed),
        "verdict": "POSITIVE_NET" if mean - cost_bps > 0 else "NON_POSITIVE_NET",
    }

