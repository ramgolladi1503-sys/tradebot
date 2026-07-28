from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from research.market_story_engine_v1.certification import run_certification
from research.market_story_engine_v1.engine import MarketStoryEngine
from research.market_story_engine_v1.scenarios import build_scenario


def terminal(kind: str) -> pd.Series:
    underlying, breadth, options = build_scenario(kind)
    return MarketStoryEngine().run(
        underlying,
        breadth,
        options,
    ).iloc[-1]


def test_bullish_market_story_requires_all_five_layers():
    output = terminal("bull")
    assert output["decision"] == "BUY_CE"
    assert output["state"] in {
        "ACCEPTED_ABOVE",
        "RETEST_HOLD_UP",
        "EXPANSION_UP",
    }
    assert bool(output["research_only"]) is True
    assert bool(output["allowed_for_live_execution"]) is False


def test_bearish_market_story_is_symmetric():
    output = terminal("bear")
    assert output["decision"] == "BUY_PE"
    assert output["state"] in {
        "ACCEPTED_BELOW",
        "RETEST_HOLD_DOWN",
        "EXPANSION_DOWN",
    }


def test_same_terminal_price_different_path_is_not_same_story():
    bullish = terminal("bull")
    false_break = terminal("false_break")
    assert bullish["decision"] == "BUY_CE"
    assert false_break["decision"] == "WAIT"
    assert bullish["state"] != false_break["state"]


@pytest.mark.parametrize(
    "kind",
    ["weak_breadth", "weak_option", "missing_option", "crossed_option"],
)
def test_incomplete_or_contradictory_evidence_blocks_buy(kind: str):
    assert terminal(kind)["decision"] == "REJECT"


def test_prefix_invariance_proves_future_rows_cannot_change_past():
    underlying, breadth, options = build_scenario("bull")
    engine = MarketStoryEngine()
    full = engine.run(underlying, breadth, options)
    prefix = engine.run(
        underlying.iloc[:-4],
        breadth.iloc[:-4],
        options.iloc[:-4],
    )
    full_values = full.iloc[: len(prefix)][
        ["decision", "state", "confidence"]
    ].reset_index(drop=True)
    prefix_values = prefix[
        ["decision", "state", "confidence"]
    ].reset_index(drop=True)
    assert full_values.equals(prefix_values)


def test_time_shifted_option_confirmation_is_not_buyable():
    underlying, breadth, options = build_scenario("bull")
    options["timestamp"] = options["timestamp"] + pd.Timedelta(minutes=10)
    output = MarketStoryEngine().run(
        underlying,
        breadth,
        options,
    ).iloc[-1]
    assert output["decision"] != "BUY_CE"


def test_duplicate_and_unsorted_timestamps_fail_closed():
    underlying, breadth, options = build_scenario("bull")
    duplicate = pd.concat(
        [underlying, underlying.iloc[[-1]]],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="duplicate"):
        MarketStoryEngine().run(duplicate, breadth, options)
    unsorted = underlying.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="strictly increasing"):
        MarketStoryEngine().run(unsorted, breadth, options)


def test_redundant_indicator_columns_do_not_change_decision():
    underlying, breadth, options = build_scenario("bull")
    base = MarketStoryEngine().run(
        underlying,
        breadth,
        options,
    ).iloc[-1]["decision"]
    underlying["ema_fast"] = underlying["close"].ewm(span=3).mean()
    underlying["ema_slow"] = underlying["close"].ewm(span=8).mean()
    underlying["supertrend_label"] = "bullish"
    output = MarketStoryEngine().run(
        underlying,
        breadth,
        options,
    ).iloc[-1]["decision"]
    assert output == base


def test_small_noise_is_stable_in_both_directions():
    engine = MarketStoryEngine()
    for kind, expected in [("bull", "BUY_CE"), ("bear", "BUY_PE")]:
        decisions = []
        for seed in range(20):
            underlying, breadth, options = build_scenario(
                kind,
                noise_seed=seed,
            )
            decisions.append(
                engine.run(underlying, breadth, options).iloc[-1]["decision"]
            )
        assert decisions.count(expected) / len(decisions) >= 0.90


def test_certification_is_deterministic_and_auditable(tmp_path: Path):
    first = run_certification(tmp_path / "a", noise_runs=10)
    second = run_certification(tmp_path / "b", noise_runs=10)
    assert first["verdict"] == "PASS_IMPLEMENTATION_ROBUSTNESS_GATE"
    assert first["semantic_sha256"] == second["semantic_sha256"]
    assert first["allowed_for_live_execution"] is False


def test_independent_auditor_does_not_import_engine():
    source = Path("scripts/audit_market_story_engine_v1.py").read_text()
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    assert not any(
        name.startswith("research.market_story_engine_v1")
        for name in imports
    )


def test_tampered_certification_fails_independent_audit(tmp_path: Path):
    from importlib.util import module_from_spec, spec_from_file_location

    run_certification(tmp_path, noise_runs=5)
    path = tmp_path / "certification.json"
    payload = json.loads(path.read_text())
    payload["baseline"]["bull"]["decision"] = "BUY_PE"
    path.write_text(json.dumps(payload))
    spec = spec_from_file_location(
        "audit_market_story",
        "scripts/audit_market_story_engine_v1.py",
    )
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.audit(path)
    assert report["verdict"] == "FAIL_INDEPENDENT_AUDIT"
    assert "semantic_hash_matches" in report["failed_checks"]
