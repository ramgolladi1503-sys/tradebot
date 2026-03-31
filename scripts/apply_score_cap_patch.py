from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "core" / "opportunity_engine.py"
TEST_FILE = ROOT / "tests" / "test_opportunity_engine_truth_guard.py"


def patch_engine() -> None:
    text = ENGINE.read_text()

    import_line = "from core.execution_quality import evaluate_pretrade_execution_quality\n"
    helper_import = "from core.execution_quality import evaluate_pretrade_execution_quality\nfrom core.opportunity_engine_score_cap_helper import apply_candidate_class_score_cap\n"
    if "from core.opportunity_engine_score_cap_helper import apply_candidate_class_score_cap" not in text:
        if import_line not in text:
            raise RuntimeError("Expected execution_quality import line not found")
        text = text.replace(import_line, helper_import, 1)

    score_line = "    score = _clamp01(score - float(execution_quality.spread_penalty or 0.0), default=0.0) or 0.0\n"
    score_block = (
        "    score = _clamp01(score - float(execution_quality.spread_penalty or 0.0), default=0.0) or 0.0\n"
        "    candidate_class = _candidate_class(candidate)\n"
        "    score, class_score_cap = apply_candidate_class_score_cap(score, candidate_class)\n"
    )
    if "score, class_score_cap = apply_candidate_class_score_cap(score, candidate_class)" not in text:
        if score_line not in text:
            raise RuntimeError("Expected score penalty line not found")
        text = text.replace(score_line, score_block, 1)

    return_anchor = '        "risk_adjusted_quality": risk_adjusted_quality,\n'
    return_insert = (
        '        "risk_adjusted_quality": risk_adjusted_quality,\n'
        '        "candidate_class": candidate_class,\n'
        '        "class_score_cap": class_score_cap,\n'
    )
    if '        "candidate_class": candidate_class,\n' not in text:
        if return_anchor not in text:
            raise RuntimeError("Expected return anchor not found")
        text = text.replace(return_anchor, return_insert, 1)

    ENGINE.write_text(text)


def patch_tests() -> None:
    text = TEST_FILE.read_text()
    old = '''    base = {\n        "trade_id": "t1",\n        "symbol": "NIFTY",\n        "execution_entry": 100.0,\n        "execution_entry_status": "executable",\n        "execution_allowed": True,\n        "tradable": True,\n        "execution_ok": True,\n        "display_entry": 100.0,\n        "display_entry_status": "displayable",\n        "builder_confidence": 0.82,\n        "permission_confidence": 0.82,\n        "gating_final_confidence": 0.82,\n        "source_flags": {},\n    }\n'''
    new = '''    base = {\n        "trade_id": "t1",\n        "symbol": "NIFTY",\n        "execution_entry": 100.0,\n        "execution_entry_status": "executable",\n        "execution_allowed": True,\n        "tradable": True,\n        "execution_ok": True,\n        "display_entry": 100.0,\n        "display_entry_status": "displayable",\n        "builder_confidence": 0.82,\n        "permission_confidence": 0.82,\n        "gating_final_confidence": 0.82,\n        "source_flags": {},\n        "quote_ok": True,\n        "best_bid": 99.5,\n        "best_ask": 100.5,\n        "spread_pct": 0.01,\n        "volume": 10000,\n        "qty_units": 10,\n        "entry_price": 100.0,\n        "stop_loss": 95.0,\n        "target": 110.0,\n    }\n'''
    if '        "best_bid": 99.5,\n' not in text:
        if old not in text:
            raise RuntimeError("Expected test base fixture block not found")
        text = text.replace(old, new, 1)

    TEST_FILE.write_text(text)


if __name__ == "__main__":
    patch_engine()
    patch_tests()
    print("Patched core/opportunity_engine.py and tests/test_opportunity_engine_truth_guard.py")
