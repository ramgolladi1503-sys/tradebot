from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "core" / "opportunity_engine.py"


def patch_engine() -> None:
    text = ENGINE.read_text()

    helper_anchor = "\n\ndef _dedupe_opportunity_candidates(candidates: Iterable[Any]) -> list[Any]:\n"
    helper_block = """\n\ndef _symbol_key(candidate: Any) -> str:\n    return str(_get_value(candidate, "symbol") or "").strip().upper()\n\n\ndef _cluster_candidates_by_symbol(\n    scored: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]],\n    *,\n    max_per_symbol: int,\n) -> list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]]:\n    if max_per_symbol <= 0:\n        return list(scored)\n\n    grouped: dict[str, list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]]] = {}\n    for item in scored:\n        symbol = _symbol_key(item[1])\n        grouped.setdefault(symbol, []).append(item)\n\n    clustered: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]] = []\n    for _symbol, rows in grouped.items():\n        rows_sorted = sorted(rows, key=lambda item: item[0], reverse=True)\n        clustered.extend(rows_sorted[:max_per_symbol])\n\n    clustered.sort(key=lambda item: item[0], reverse=True)\n    return clustered\n"""
    if "def _cluster_candidates_by_symbol(" not in text:
        if helper_anchor not in text:
            raise RuntimeError("Expected dedupe helper anchor not found")
        text = text.replace(helper_anchor, helper_block + helper_anchor, 1)

    sort_line = "    scored.sort(key=lambda item: item[0], reverse=True)\n"
    cluster_block = (
        "    scored.sort(key=lambda item: item[0], reverse=True)\n"
        '    max_per_symbol = max(0, int(getattr(cfg, "OPPORTUNITY_MAX_PER_SYMBOL", 2) or 0))\n'
        "    scored = _cluster_candidates_by_symbol(scored, max_per_symbol=max_per_symbol)\n"
    )
    if (
        "scored = _cluster_candidates_by_symbol(scored, max_per_symbol=max_per_symbol)"
        not in text
    ):
        occurrences = text.count(sort_line)
        if occurrences < 1:
            raise RuntimeError("Expected scored.sort line not found")
        text = text.replace(sort_line, cluster_block, 1)

    source_flags_anchor = '                "selection_reason": selection_reason,\n'
    source_flags_insert = (
        '                "selection_reason": selection_reason,\n'
        '                "cluster_symbol": _symbol_key(candidate),\n'
    )
    if '                "cluster_symbol": _symbol_key(candidate),\n' not in text:
        if source_flags_anchor not in text:
            raise RuntimeError("Expected source_flags insertion anchor not found")
        text = text.replace(source_flags_anchor, source_flags_insert, 1)

    dict_update_anchor = '                    "selection_reason": selection_reason,\n'
    dict_update_insert = (
        '                    "selection_reason": selection_reason,\n'
        '                    "cluster_symbol": _symbol_key(candidate),\n'
    )
    if (
        text.count('                    "cluster_symbol": _symbol_key(candidate),\n')
        == 0
    ):
        if dict_update_anchor not in text:
            raise RuntimeError("Expected dict update insertion anchor not found")
        text = text.replace(dict_update_anchor, dict_update_insert, 1)

    replace_anchor = "                selection_reason=selection_reason,\n"
    replace_insert = (
        "                selection_reason=selection_reason,\n"
        "                cluster_symbol=_symbol_key(candidate),\n"
    )
    if "                cluster_symbol=_symbol_key(candidate),\n" not in text:
        if replace_anchor not in text:
            raise RuntimeError("Expected replace insertion anchor not found")
        text = text.replace(replace_anchor, replace_insert, 1)

    ENGINE.write_text(text)


if __name__ == "__main__":
    patch_engine()
    print("Patched core/opportunity_engine.py with symbol clustering")
