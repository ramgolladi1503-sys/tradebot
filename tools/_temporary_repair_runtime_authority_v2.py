from pathlib import Path


def replace_once(path_text: str, old: str, new: str) -> None:
    path = Path(path_text)
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_CONTEXT_COUNT:{path_text}:{count}:{old[:80]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


replace_once(
    'core/canonical_execution_decision.py',
    '''        or signals.get("execution_allowed_raw") is False\n        or signals.get("eligible_for_execution_raw") is False\n''',
    '',
)

replace_once(
    'core/opportunity_engine.py',
    '''    executable = [candidate for candidate in stamped if authority_allows_execution(candidate)]\n    result = _RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY(\n        executable,\n''',
    '''    executable = [candidate for candidate in stamped if authority_allows_execution(candidate)]\n    selection_pool = executable if mode in {"LIVE", "REAL"} else stamped\n    result = _RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY(\n        selection_pool,\n''',
)

print('second runtime authority repair applied')
