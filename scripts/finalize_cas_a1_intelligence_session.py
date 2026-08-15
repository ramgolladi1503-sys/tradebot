from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.cas_a1 import (
    CasA1Observation,
    ConstituentMark,
    append_events,
    build_cas_a1_events,
    cumulative_summary,
    evaluate_cas_a1,
    write_prospective_result,
)
from aixion_trade_intelligence.storage import atomic_write_json


def _dt(value: Any, field: str) -> datetime:
    from aixion_trade_intelligence.contracts import parse_timestamp

    if value in (None, ""):
        raise SystemExit(f"{field} is required")
    return parse_timestamp(value, field_name=field)


def _load_observation(path: Path) -> tuple[CasA1Observation, dict[str, Any]]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit("CAS-A1 input must be a JSON object")
    contract = raw.get("analytics_contract")
    if not isinstance(contract, dict):
        raise SystemExit("analytics_contract is required")

    marks_raw = raw.get("constituent_marks")
    if not isinstance(marks_raw, list):
        raise SystemExit("constituent_marks must be a list")
    marks = tuple(
        ConstituentMark(
            instrument_key=str(row.get("instrument_key") or "").strip(),
            price_1510=row.get("price_1510"),
            price_1514=row.get("price_1514"),
            source_event_ids=tuple(row.get("source_event_ids") or ()),
        )
        for row in marks_raw
        if isinstance(row, dict)
    )

    observation = CasA1Observation(
        session_id=str(raw.get("session_id") or "").strip(),
        session_date=str(raw.get("session_date") or "").strip(),
        index_instrument=str(raw.get("index_instrument") or "").strip(),
        futures_instrument=str(raw.get("futures_instrument") or "").strip(),
        constituent_marks=marks,
        nifty_1514=raw.get("nifty_1514"),
        nifty_1514_available_time=_dt(raw.get("nifty_1514_available_time"), "nifty_1514_available_time"),
        final_cas_index=raw.get("final_cas_index"),
        final_cas_available_time=_dt(raw.get("final_cas_available_time"), "final_cas_available_time"),
        future_1529=raw.get("future_1529"),
        future_1529_available_time=_dt(raw.get("future_1529_available_time"), "future_1529_available_time"),
        future_1539=raw.get("future_1539"),
        future_1539_available_time=_dt(raw.get("future_1539_available_time"), "future_1539_available_time"),
        source_provider=str(raw.get("source_provider") or "").strip(),
        source_event_ids=tuple(raw.get("source_event_ids") or ()),
    )
    return observation, contract


def _markdown(result: dict[str, Any], cumulative: dict[str, Any]) -> str:
    correct = result.get("correct")
    result_text = "NO_PREDICTION" if correct is None else ("CORRECT" if correct else "INCORRECT")
    return f"""# CAS-A1 prospective analytics — {result['session_date']}

## Frozen spec

- version: `{result['spec_version']}`
- spec SHA-256: `{result['spec_sha256']}`
- refit: `false`
- threshold search: `false`

## Expectation

- frozen constituent count: `{result['constituent_count']}`
- equal-weight 15:10→15:14 return: `{result['equal_weight_return_1510_1514_bps']:.6f} bps`
- expected CAS adjustment: `{result['expected_cas_adjustment_bps']:.6f} bps`

## Auction

- NIFTY 15:14: `{result['nifty_1514']}`
- final CAS index: `{result['final_cas_index']}`
- final CAS available: `{result['final_cas_available_time']}`
- realized CAS adjustment: `{result['realized_cas_adjustment_bps']:.6f} bps`
- auction surprise: `{result['auction_surprise_bps']:.6f} bps`

## Frozen prediction / outcome

- prediction: **{result['prediction']}**
- futures 15:29: `{result['future_1529']}`
- futures 15:39: `{result['future_1539']}`
- futures 15:29→15:39: `{result['future_1529_1539_bps']:.6f} bps`
- actual sign: **{result['actual_sign']}**
- result: **{result_text}**

## Prospective ledger

- prospective sessions: `{cumulative['prospective_sessions']}`
- scored sessions: `{cumulative['scored_sessions']}`
- correct: `{cumulative['correct']}`
- incorrect: `{cumulative['incorrect']}`
- no-prediction: `{cumulative['no_prediction']}`
- directional accuracy: `{cumulative['directional_accuracy']}`
- development and prospective pooled: `false`

## Claim boundary

```text
PROSPECTIVE_SUPPORTED=false
HISTORICAL_EDGE_SUPPORTED=false
OUT_OF_SAMPLE_SUPPORTED=false
EXECUTION_VIABLE=false
STRUCTURAL_EDGE_CERTIFIED=false
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize one frozen CAS-A1 prospective analytics session")
    parser.add_argument("--input", type=Path, required=True, help="Validated post-close CAS-A1 observation JSON")
    parser.add_argument("--events", type=Path, required=True, help="PR790 canonical event JSONL")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(".runtime/aixion_trade_intelligence/cas_a1/prospective"),
    )
    args = parser.parse_args()

    observation, contract = _load_observation(args.input)
    result = evaluate_cas_a1(observation, contract)
    events = build_cas_a1_events(observation, contract)

    args.output_root.mkdir(parents=True, exist_ok=True)
    result_path = write_prospective_result(result=result, output_dir=args.output_root / "sessions")
    append_events(args.events, events)

    cumulative = cumulative_summary(args.output_root / "sessions")
    atomic_write_json(args.output_root / "cumulative_summary.json", cumulative)
    report_path = args.output_root / f"{result.session_date}_CAS_A1_REPORT.md"
    report_path.write_text(_markdown(result.to_dict(), cumulative))

    print(json.dumps({
        "status": "CAS_A1_PROSPECTIVE_SESSION_FINALIZED",
        "session_id": result.session_id,
        "session_date": result.session_date,
        "prediction": result.prediction,
        "actual_sign": result.actual_sign,
        "correct": result.correct,
        "result_path": str(result_path),
        "report_path": str(report_path),
        "cumulative_path": str(args.output_root / "cumulative_summary.json"),
        "canonical_events_appended": len(events),
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
