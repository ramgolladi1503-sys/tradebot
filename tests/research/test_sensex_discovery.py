import hashlib
import json

from research.banknifty_v1.discovery import evaluate, load_artifact
from research.governance.index_research_contract import ResearchOutcome, ResearchSpec


def test_sensex_reuses_causal_evaluator_without_banknifty_identity_alias(tmp_path):
    candles = []
    for day, close, opening in [("2023-01-02", 100.0, 101.0), ("2023-01-03", 102.0, 101.5), ("2023-01-04", 103.0, 104.0), ("2023-01-05", 105.0, 104.5), ("2023-01-06", 106.0, 107.0), ("2023-01-09", 108.0, 107.5)]:
        candles.extend([[f"{day}T15:29:00+05:30", close, close, close, close, 0, 0], [f"{day}T09:15:00+05:30", opening, opening, opening, opening, 0, 0]])
    path = tmp_path / "sensex.json"
    path.write_text(json.dumps({"data": {"candles": candles}}), encoding="utf-8")
    artifact = load_artifact(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    spec = ResearchSpec("SENSEX", "next_session_open_gap", "09:14:59", "dev", "oos", ("prior_close_gap_baseline",), ("sign_permutation",), "required")
    report = evaluate(spec, [artifact])
    assert report.outcome is ResearchOutcome.NO_STRUCTURAL_EDGE_FOUND
