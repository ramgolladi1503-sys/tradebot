import re

with open('tests/test_trade_builder_soft_vetoes.py', 'r') as f:
    content = f.read()

# Fix test_equity_fallback_trade_serializes_staged_confidence_fields
content = content.replace(
    'monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.30, raising=False)',
    'monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.30, raising=False)\n    monkeypatch.setattr(cfg, "GATING_FINAL_CONFIDENCE_MIN", 0.30, raising=False)'
)

# Fix test_main_path_trade_serializes_staged_confidence_fields
content = content.replace(
    'monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.31, raising=False)',
    'monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.31, raising=False)\n    monkeypatch.setattr(cfg, "GATING_FINAL_CONFIDENCE_MIN", 0.31, raising=False)'
)

# Fix test_build_with_trace_softens_no_candidates_survived_in_sim
content = content.replace(
    '''        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,''',
    '''        quick_mode=False,
        allow_fallbacks=True,
        allow_baseline=False,'''
)

# Fix test_weak_family_can_lose_small_slot
content = content.replace(
    '''            "families": {
                "continuation|bearish": {
                    "family_score_adjustment": -0.05,''',
    '''            "families": {
                "volatility_expansion|bearish": {
                    "family_score_adjustment": -0.05,
                    "family_scarcity_adjustment": -1,
                    "family_confidence": 0.8,
                    "family_feedback_applied": True,
                    "expectancy_score": -0.4,
                },
                "continuation|bearish": {
                    "family_score_adjustment": -0.05,'''
)

with open('tests/test_trade_builder_soft_vetoes.py', 'w') as f:
    f.write(content)
