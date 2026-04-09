from core.opportunity_book import build_opportunity_book
from core.elite_swap import should_replace


def _score_of_active(active_trade):
    if not active_trade:
        return None
    try:
        return float(active_trade.get("score", active_trade.get("final_score", 0.0)))
    except Exception:
        return 0.0


def run_opportunity_pipeline(candidates, active_trade=None, min_enter_score=0.7, top_n=3):
    book = build_opportunity_book(candidates or [])
    if not book:
        return {
            "state": "NO_TRADE",
            "reason": "no_candidates",
            "ranked": [],
            "selected": None,
        }

    ranked = book[: max(1, int(top_n or 1))]
    top = ranked[0]
    active_score = _score_of_active(active_trade)

    if active_trade and should_replace(active_score, top.score):
        return {
            "state": "REPLACE",
            "reason": "elite_swap",
            "ranked": ranked,
            "selected": top,
        }

    if active_trade:
        return {
            "state": "HOLD",
            "reason": "no_significant_upgrade",
            "ranked": ranked,
            "selected": active_trade,
        }

    if float(top.score) >= float(min_enter_score):
        return {
            "state": "ENTER",
            "reason": "top_ranked",
            "ranked": ranked,
            "selected": top,
        }

    return {
        "state": "WATCHLIST",
        "reason": "score_too_low",
        "ranked": ranked,
        "selected": top,
    }
