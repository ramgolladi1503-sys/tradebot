from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from strategies.pro_layer.alpha_validation import validate_alpha_edge
from strategies.pro_layer.pro_shadow_logger import DEFAULT_SHADOW_LOG_PATH, load_shadow_records
from strategies.pro_layer.strategy_lifecycle import decide_strategy_lifecycle


def build_report(rows: list[dict], *, min_trades: int = 30) -> dict:
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    by_strategy_regime: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        strategy = str(row.get("strategy") or "unknown")
        regime = str(row.get("regime") or "UNKNOWN")
        by_strategy[strategy].append(row)
        by_strategy_regime[(strategy, regime)].append(row)

    strategies = []
    for strategy, strat_rows in sorted(by_strategy.items()):
        alpha = validate_alpha_edge(strat_rows, strategy=strategy, min_trades=min_trades)
        lifecycle = decide_strategy_lifecycle(strat_rows, strategy=strategy, current_state="SHADOW", min_trades=min_trades)
        regimes = []
        for (s, regime), regime_rows in sorted(by_strategy_regime.items()):
            if s != strategy:
                continue
            regime_report = validate_alpha_edge(regime_rows, strategy=strategy, min_trades=max(5, min_trades // 3))
            regimes.append({"regime": regime, **regime_report.as_dict()})
        strategies.append(
            {
                "strategy": strategy,
                "alpha": alpha.as_dict(),
                "lifecycle": lifecycle.as_dict(),
                "regimes": regimes,
            }
        )
    return {"rows": len(rows), "strategies": strategies}


def main() -> None:
    rows = load_shadow_records(path=DEFAULT_SHADOW_LOG_PATH)
    report = build_report(rows)
    out_path = Path("logs/pro_alpha_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
