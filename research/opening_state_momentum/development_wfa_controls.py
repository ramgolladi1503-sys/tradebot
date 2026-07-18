import random
from typing import List, Dict, Any, Tuple
from research.opening_state_momentum.development_wfa_metrics import calculate_metrics

def bootstrap_confidence_intervals(
    returns: List[float], 
    num_resamples: int, 
    seed: int, 
    friction: float = 0.0
) -> Dict[str, Any]:
    """
    Deterministic non-parametric bootstrap.
    Calculates 95% percentile intervals for mean, median, win rate, and profit factor.
    """
    n = len(returns)
    if n == 0:
        return {}
        
    rng = random.Random(seed)
    
    means = []
    medians = []
    win_rates = []
    profit_factors = []
    
    for _ in range(num_resamples):
        sample = [rng.choice(returns) for _ in range(n)]
        metrics = calculate_metrics(sample, friction)
        
        means.append(metrics["mean_return"])
        medians.append(metrics["median_return"])
        win_rates.append(metrics["win_rate"])
        
        pf = metrics["profit_factor"]
        if isinstance(pf, dict):
            pass # Skip undefined profit factors from percentile
        elif pf is not None:
            profit_factors.append(pf)
            
    means.sort()
    medians.sort()
    win_rates.sort()
    profit_factors.sort()
    
    def get_interval(sorted_list):
        if not sorted_list:
            return None
        length = len(sorted_list)
        p025 = sorted_list[int(length * 0.025)]
        p975 = sorted_list[int(length * 0.975)]
        return [p025, p975]
        
    return {
        "mean_return_95_ci": get_interval(means),
        "median_return_95_ci": get_interval(medians),
        "win_rate_95_ci": get_interval(win_rates),
        "profit_factor_95_ci": get_interval(profit_factors)
    }

def calculate_return_from_prices(entry_price: float, exit_price: float, direction: str) -> float:
    if direction == "LONG":
        return (exit_price - entry_price) / entry_price
    elif direction == "SHORT":
        return (entry_price - exit_price) / entry_price
    return 0.0

def inverted_direction_control(
    outcomes: List[Dict[str, Any]], 
    friction: float = 0.0
) -> Dict[str, Any]:
    """
    Inverts the returns (LONG -> SHORT, SHORT -> LONG) by negating the return before friction.
    """
    inverted_returns = []
    
    for outcome in outcomes:
        orig_dir = outcome["direction"]
        inverted_dir = "SHORT" if orig_dir == "LONG" else ("LONG" if orig_dir == "SHORT" else "NONE")
        r = calculate_return_from_prices(outcome["entry_price"], outcome["exit_price"], inverted_dir)
        inverted_returns.append(r)
        
    metrics = calculate_metrics(inverted_returns, friction)
    return metrics

def direction_randomization_control(
    outcomes: List[Dict[str, Any]], 
    num_permutations: int,
    seed: int,
    friction: float = 0.0,
    actual_mean: float = 0.0
) -> Dict[str, Any]:
    """
    Randomly permutes direction (LONG or SHORT) while preserving counts.
    """
    n = len(outcomes)
    if n == 0:
        return {}
        
    original_directions = [o["direction"] for o in outcomes]
    num_long = original_directions.count("LONG")
    num_short = original_directions.count("SHORT")
    
    rng = random.Random(seed)
    
    null_means = []
    
    # We create a list of exact directions we need to assign
    fixed_directions = ["LONG"] * num_long + ["SHORT"] * num_short
    
    for _ in range(num_permutations):
        shuffled_dirs = fixed_directions[:]
        rng.shuffle(shuffled_dirs)
        
        simulated_returns = []
        for i, outcome in enumerate(outcomes):
            r = calculate_return_from_prices(outcome["entry_price"], outcome["exit_price"], shuffled_dirs[i])
            simulated_returns.append(r)
            
        metrics = calculate_metrics(simulated_returns, friction)
        null_means.append(metrics["mean_return"])
        
    null_means.sort()
    
    # Compute one-sided empirical p-value for actual_mean > null_means
    # How many null_means are >= actual_mean?
    count_geq = sum(1 for m in null_means if m >= actual_mean)
    p_value = count_geq / num_permutations
    
    percentile_rank = (1.0 - p_value) * 100
    
    null_mean_avg = sum(null_means) / num_permutations
    if num_permutations > 1:
        variance = sum((m - null_mean_avg)**2 for m in null_means) / (num_permutations - 1)
        null_std = variance ** 0.5
    else:
        null_std = 0.0
        
    return {
        "actual_mean": actual_mean,
        "null_mean": null_mean_avg,
        "null_standard_deviation": null_std,
        "empirical_p_value": p_value,
        "percentile_rank": percentile_rank
    }

def chronological_concentration_control(
    returns: List[float],
    num_permutations: int,
    seed: int,
    friction: float = 0.0,
    actual_max_drawdown: float = 0.0,
    actual_longest_losing_streak: int = 0
) -> Dict[str, Any]:
    """
    Randomly permutes the order of the fixed realized returns.
    """
    n = len(returns)
    if n == 0:
        return {}
        
    rng = random.Random(seed)
    
    null_drawdowns = []
    null_streaks = []
    
    for _ in range(num_permutations):
        shuffled_returns = returns[:]
        rng.shuffle(shuffled_returns)
        
        metrics = calculate_metrics(shuffled_returns, friction)
        null_drawdowns.append(metrics["maximum_drawdown"])
        null_streaks.append(metrics["longest_losing_streak"])
        
    null_drawdowns.sort()
    null_streaks.sort()
    
    def p_value_greater_equal(actual, null_dist):
        return sum(1 for val in null_dist if val >= actual) / num_permutations
        
    return {
        "actual_max_drawdown": actual_max_drawdown,
        "drawdown_p_value": p_value_greater_equal(actual_max_drawdown, null_drawdowns),
        "actual_longest_losing_streak": actual_longest_losing_streak,
        "losing_streak_p_value": p_value_greater_equal(actual_longest_losing_streak, null_streaks)
    }
