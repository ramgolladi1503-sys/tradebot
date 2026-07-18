import math
from typing import List, Dict, Any, Tuple

def wilson_score_interval(wins: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """
    Calculates the Wilson score interval for a binomial proportion.
    Uses z=1.96 for 95% confidence interval.
    """
    if n == 0:
        return (None, None)
    
    # 95% confidence level
    z = 1.95996
    
    p = wins / n
    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    spread = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (lower, upper)

def calculate_metrics(returns: List[float], friction: float = 0.0) -> Dict[str, Any]:
    """
    Calculates all required WFA metrics on a chronologically ordered list of returns.
    `friction` is applied per side, so total friction per trade = 2 * friction.
    If the return list is empty, returns appropriate null values or 0 for counts.
    """
    n = len(returns)
    if n == 0:
        return {
            "trade_count": 0,
            "positive_return_count": 0,
            "negative_return_count": 0,
            "zero_return_count": 0,
            "mean_return": None,
            "median_return": None,
            "standard_deviation": None,
            "standard_error": None,
            "minimum": None,
            "maximum": None,
            "25th_percentile": None,
            "75th_percentile": None,
            "win_rate": None,
            "wilson_95_win_rate_interval": None,
            "average_winner": None,
            "average_loser": None,
            "payoff_ratio": None,
            "profit_factor": None,
            "expectancy": None,
            "cumulative_arithmetic_return": 0.0,
            "cumulative_compounded_return": 0.0,
            "maximum_drawdown": 0.0,
            "longest_winning_streak": 0,
            "longest_losing_streak": 0
        }
        
    net_returns = [r - (2 * friction) for r in returns]
    
    positives = [r for r in net_returns if r > 0]
    negatives = [r for r in net_returns if r < 0]
    zeros = [r for r in net_returns if r == 0]
    
    pos_count = len(positives)
    neg_count = len(negatives)
    zero_count = len(zeros)
    
    mean_ret = sum(net_returns) / n
    sorted_ret = sorted(net_returns)
    
    # Median
    mid = n // 2
    if n % 2 == 0:
        median_ret = (sorted_ret[mid - 1] + sorted_ret[mid]) / 2
    else:
        median_ret = sorted_ret[mid]
        
    # Variance and StdDev
    if n > 1:
        variance = sum((r - mean_ret)**2 for r in net_returns) / (n - 1)
        std_dev = math.sqrt(variance)
        std_err = std_dev / math.sqrt(n)
    else:
        std_dev = 0.0
        std_err = 0.0
        
    min_ret = sorted_ret[0]
    max_ret = sorted_ret[-1]
    
    # Percentiles
    def percentile(p, data):
        k = (len(data) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        d0 = data[int(f)] * (c - k)
        d1 = data[int(c)] * (k - f)
        return d0 + d1
        
    p25 = percentile(0.25, sorted_ret)
    p75 = percentile(0.75, sorted_ret)
    
    win_rate = pos_count / n
    wilson_interval = wilson_score_interval(pos_count, n)
    
    avg_win = sum(positives) / pos_count if pos_count > 0 else None
    avg_loss = sum(negatives) / neg_count if neg_count > 0 else None
    
    if avg_win is not None and avg_loss is not None and avg_loss != 0:
        payoff_ratio = abs(avg_win / avg_loss)
    else:
        payoff_ratio = None
        
    sum_win = sum(positives)
    sum_loss = sum(negatives)
    
    if sum_loss == 0:
        if sum_win > 0:
            profit_factor = {"value": None, "reason": "No losses to divide by"}
        else:
            profit_factor = {"value": None, "reason": "No wins or losses"}
    else:
        profit_factor = {"value": abs(sum_win / sum_loss), "reason": None}
        
    expectancy = mean_ret
    cum_arithmetic = sum(net_returns)
    
    cum_compounded = 1.0
    compounded_path = [1.0]
    for r in net_returns:
        cum_compounded *= (1 + r)
        compounded_path.append(cum_compounded)
        
    total_compounded_return = cum_compounded - 1.0
    
    max_dd = 0.0
    peak = compounded_path[0]
    for val in compounded_path:
        if val > peak:
            peak = val
        dd = (peak - val) / peak
        if dd > max_dd:
            max_dd = dd
            
    longest_win_streak = 0
    longest_lose_streak = 0
    current_win = 0
    current_lose = 0
    
    for r in net_returns:
        if r > 0:
            current_win += 1
            current_lose = 0
            if current_win > longest_win_streak:
                longest_win_streak = current_win
        elif r < 0:
            current_lose += 1
            current_win = 0
            if current_lose > longest_lose_streak:
                longest_lose_streak = current_lose
        else:
            current_win = 0
            current_lose = 0
            
    # Remove reason if it's just a number
    pf_out = profit_factor["value"] if profit_factor["value"] is not None else {"null_reason": profit_factor["reason"]}

    return {
        "trade_count": n,
        "positive_return_count": pos_count,
        "negative_return_count": neg_count,
        "zero_return_count": zero_count,
        "mean_return": mean_ret,
        "median_return": median_ret,
        "standard_deviation": std_dev,
        "standard_error": std_err,
        "minimum": min_ret,
        "maximum": max_ret,
        "25th_percentile": p25,
        "75th_percentile": p75,
        "win_rate": win_rate,
        "wilson_95_win_rate_interval": list(wilson_interval),
        "average_winner": avg_win,
        "average_loser": avg_loss,
        "payoff_ratio": payoff_ratio,
        "profit_factor": pf_out,
        "expectancy": expectancy,
        "cumulative_arithmetic_return": cum_arithmetic,
        "cumulative_compounded_return": total_compounded_return,
        "maximum_drawdown": max_dd,
        "longest_winning_streak": longest_win_streak,
        "longest_losing_streak": longest_lose_streak
    }
