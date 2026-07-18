import math
from typing import List, Dict, Any

def get_null_metric(reason: str) -> Dict[str, Any]:
    return {"value": None, "reason": reason}

def validate_outcome_returns(outcomes: List[Dict[str, Any]]) -> int:
    """
    Validates that the frozen returns match the recomputed returns.
    Returns the number of mismatches (should be 0).
    """
    mismatches = 0
    tolerance = 1e-15
    for o in outcomes:
        direction = o["direction"]
        if direction not in ("LONG", "SHORT"):
            mismatches += 1
            continue
            
        entry = o["entry_price"]
        exit_p = o["exit_price"]
        stored_gross = o["gross_return"]
        
        if direction == "LONG":
            recomputed_gross = exit_p / entry - 1.0
        else:
            recomputed_gross = entry / exit_p - 1.0
            
        if not math.isclose(stored_gross, recomputed_gross, abs_tol=tolerance):
            mismatches += 1
            
        for bps, field in [(0.0, "net_return_0bps"), (2.0, "net_return_2bps"), 
                           (5.0, "net_return_5bps"), (10.0, "net_return_10bps")]:
            stored_net = o[field]
            recomputed_net = stored_gross - 2 * bps / 10000.0
            if not math.isclose(stored_net, recomputed_net, abs_tol=tolerance):
                mismatches += 1
                
    return mismatches

def calculate_metrics(returns: List[float]) -> Dict[str, Any]:
    if not returns:
        return {
            "trade_count": 0,
            "positive_return_count": 0,
            "negative_return_count": 0,
            "zero_return_count": 0,
            "mean_return": get_null_metric("empty_sample"),
            "median_return": get_null_metric("empty_sample"),
            "standard_deviation": get_null_metric("empty_sample"),
            "standard_error": get_null_metric("empty_sample"),
            "minimum": get_null_metric("empty_sample"),
            "maximum": get_null_metric("empty_sample"),
            "25th_percentile": get_null_metric("empty_sample"),
            "75th_percentile": get_null_metric("empty_sample"),
            "win_rate": get_null_metric("empty_sample"),
            "wilson_95_win_rate_interval": get_null_metric("empty_sample"),
            "average_winner": get_null_metric("empty_sample"),
            "average_loser": get_null_metric("empty_sample"),
            "payoff_ratio": get_null_metric("empty_sample"),
            "profit_factor": get_null_metric("empty_sample"),
            "expectancy": get_null_metric("empty_sample"),
            "cumulative_arithmetic_return": 0.0,
            "cumulative_compounded_return": 1.0,
            "maximum_drawdown": 0.0,
            "longest_winning_streak": 0,
            "longest_losing_streak": 0
        }

    n = len(returns)
    pos_returns = [r for r in returns if r > 0]
    neg_returns = [r for r in returns if r < 0]
    zero_returns = [r for r in returns if r == 0]
    
    pos_count = len(pos_returns)
    neg_count = len(neg_returns)
    zero_count = len(zero_returns)

    mean = sum(returns) / n
    
    s_rets = sorted(returns)
    if n % 2 == 0:
        median = (s_rets[n // 2 - 1] + s_rets[n // 2]) / 2.0
    else:
        median = s_rets[n // 2]
        
    if n > 1:
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std_dev = math.sqrt(variance)
        std_err = std_dev / math.sqrt(n)
    else:
        std_dev = get_null_metric("n_too_small")
        std_err = get_null_metric("n_too_small")

    minimum = s_rets[0]
    maximum = s_rets[-1]

    def percentile(data, p):
        idx = (len(data) - 1) * p
        lower = math.floor(idx)
        upper = math.ceil(idx)
        weight = idx - lower
        return data[lower] * (1 - weight) + data[upper] * weight

    p25 = percentile(s_rets, 0.25)
    p75 = percentile(s_rets, 0.75)

    win_rate = pos_count / n
    
    # Wilson interval
    z = 1.96
    denominator = 1 + z**2/n
    center = (win_rate + z**2 / (2*n)) / denominator
    spread = z * math.sqrt(win_rate*(1 - win_rate)/n + z**2/(4*n**2)) / denominator
    wilson_lower = center - spread
    wilson_upper = center + spread

    avg_win = sum(pos_returns) / pos_count if pos_count > 0 else get_null_metric("no_winners")
    avg_loss = sum(neg_returns) / neg_count if neg_count > 0 else get_null_metric("no_losers")
    
    if isinstance(avg_win, float) and isinstance(avg_loss, float) and avg_loss != 0:
        payoff_ratio = abs(avg_win / avg_loss)
    else:
        payoff_ratio = get_null_metric("undefined_components")
        
    sum_pos = sum(pos_returns)
    sum_neg = sum(neg_returns)
    if sum_neg != 0:
        profit_factor = abs(sum_pos / sum_neg)
    else:
        profit_factor = get_null_metric("zero_loss_denominator")

    if isinstance(avg_win, float) and isinstance(avg_loss, float):
        loss_rate = neg_count / n
        expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
    else:
        expectancy = get_null_metric("undefined_components")

    cum_ar = sum(returns)
    cum_comp = 1.0
    for r in returns:
        cum_comp *= (1 + r)
        
    peak = 1.0
    max_dd = 0.0
    current_comp = 1.0
    for r in returns:
        current_comp *= (1 + r)
        if current_comp > peak:
            peak = current_comp
        dd = (peak - current_comp) / peak
        if dd > max_dd:
            max_dd = dd

    max_win_streak = 0
    max_lose_streak = 0
    curr_win = 0
    curr_lose = 0
    for r in returns:
        if r > 0:
            curr_win += 1
            curr_lose = 0
            if curr_win > max_win_streak:
                max_win_streak = curr_win
        elif r < 0:
            curr_lose += 1
            curr_win = 0
            if curr_lose > max_lose_streak:
                max_lose_streak = curr_lose
        else:
            curr_win = 0
            curr_lose = 0

    return {
        "trade_count": n,
        "positive_return_count": pos_count,
        "negative_return_count": neg_count,
        "zero_return_count": zero_count,
        "mean_return": mean,
        "median_return": median,
        "standard_deviation": std_dev,
        "standard_error": std_err,
        "minimum": minimum,
        "maximum": maximum,
        "25th_percentile": p25,
        "75th_percentile": p75,
        "win_rate": win_rate,
        "wilson_95_win_rate_interval": [wilson_lower, wilson_upper],
        "average_winner": avg_win,
        "average_loser": avg_loss,
        "payoff_ratio": payoff_ratio,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "cumulative_arithmetic_return": cum_ar,
        "cumulative_compounded_return": cum_comp,
        "maximum_drawdown": max_dd,
        "longest_winning_streak": max_win_streak,
        "longest_losing_streak": max_lose_streak
    }
