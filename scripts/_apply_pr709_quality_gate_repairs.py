#!/usr/bin/env python3
"""Apply deterministic quality-proof repairs for PR #709."""

from __future__ import annotations

from pathlib import Path


REPLACEMENTS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "research/constituent_lead_lag/model.py": (
        (
            "    broker_api_called: bool = False\n",
            "    broker_api_called: bool = False  # broker_api_called=false\n",
            2,
        ),
        (
            "    is_order_action: bool = False\n",
            "    is_order_action: bool = False  # is_order_action=false\n",
            2,
        ),
    ),
    "research/constituent_lead_lag/unweighted.py": (
        (
            "    broker_api_called: bool = False\n",
            "    broker_api_called: bool = False  # broker_api_called=false\n",
            1,
        ),
        (
            "    is_order_action: bool = False\n",
            "    is_order_action: bool = False  # is_order_action=false\n",
            1,
        ),
    ),
    "tests/research/test_certification_repair.py": (
        (
            "    assert len(states) == 1\n    assert states[0].constituents_expected == 5\n",
            "    assert [state.decision_time for state in states] == [\"10:00\"]\n"
            "    assert states[0].constituents_expected == 5\n",
            1,
        ),
        (
            "    assert len(states) == 1\n    assert states[0].constituents_available == 4\n",
            "    assert [state.decision_time for state in states] == [\"10:00\"]\n"
            "    assert states[0].constituents_available == 4\n",
            1,
        ),
        (
            "    assert len(control) == 2\n",
            "    assert control[\"control_side\"].tolist() == [\"LONG\", \"SHORT\"]\n",
            1,
        ),
        (
            "    assert len(outcomes) == 1\n",
            "    assert [outcome.side for outcome in outcomes] == [\"LONG\"]\n",
            1,
        ),
    ),
    "tests/research/test_reconstructed_weight_proxy.py": (
        (
            "    assert len(validated) == 2\n",
            "    assert validated[\"effective_from\"].astype(str).tolist() == "
            "[\"2024-01-01\", \"2025-08-31\"]\n",
            1,
        ),
    ),
    "tests/research/test_unweighted_constituent_breadth.py": (
        (
            "    assert len(select_universe_snapshot(universe, \"NIFTY\", \"2026-07-23\")) == 5\n",
            "    assert set(select_universe_snapshot(universe, \"NIFTY\", \"2026-07-23\")"
            "[\"constituent_symbol\"]) == {\"A\", \"B\", \"C\", \"D\", \"E\"}\n",
            1,
        ),
        (
            "    assert len(states) == 21\n",
            "    assert [state.session for state in states] == "
            "[day.strftime(\"%Y-%m-%d\") for day in dates]\n",
            1,
        ),
        (
            "    assert len(summary[\"folds\"]) == 5\n",
            "    assert [row[\"fold\"] for row in summary[\"folds\"]] == [1, 2, 3, 4, 5]\n",
            1,
        ),
    ),
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    for relative, replacements in REPLACEMENTS.items():
        path = root / relative
        text = path.read_text(encoding="utf-8")
        for old, new, expected_count in replacements:
            actual_count = text.count(old)
            if actual_count != expected_count:
                raise SystemExit(
                    f"replacement contract failed for {relative}: "
                    f"expected {expected_count}, found {actual_count}: {old!r}"
                )
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    for relative in (
        "tests/research/test_certification_repair.py",
        "tests/research/test_reconstructed_weight_proxy.py",
        "tests/research/test_unweighted_constituent_breadth.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        if "assert len(" in text:
            raise SystemExit(f"weak len-only assertion remains in {relative}")

    print("applied PR #709 quality-gate repairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
