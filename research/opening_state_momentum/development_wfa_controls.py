import random
import math
from typing import List, Dict, Any
from research.opening_state_momentum.development_wfa_metrics import calculate_metrics

def bootstrap_confidence_intervals(returns: List[float], iterations: int, seed: int, friction_bps: float = 0.0) -> Dict[str, Any]:
    rng = random.Random(seed)
    n = len(returns)
    means = []
    
    for _ in range(iterations):
        sample = [rng.choice(returns) for _ in range(n)]
        mean = sum(sample) / n
        means.append(mean)
        
    means.sort()
    lower = means[int((iterations - 1) * 0.025)]
    upper = means[int((iterations - 1) * 0.975)]
    
    return {
        "bootstrap_iterations": iterations,
        "mean_95_percent_interval": [lower, upper]
    }

def inverted_direction_control(outcomes: List[Dict[str, Any]], friction_bps: float) -> Dict[str, Any]:
    inverted_returns = []
    for o in outcomes:
        direction = o["direction"]
        entry = o["entry_price"]
        exit_p = o["exit_price"]
        
        # Invert the original formula
        if direction == "LONG":
            inverted_gross = entry / exit_p - 1.0
        else:
            inverted_gross = exit_p / entry - 1.0
            
        inverted_net = inverted_gross - 2 * friction_bps / 10000.0
        inverted_returns.append(inverted_net)
        
    return calculate_metrics(inverted_returns)

def direction_randomization_control(outcomes: List[Dict[str, Any]], iterations: int, seed: int, friction_bps: float, actual_mean: float) -> Dict[str, Any]:
    rng = random.Random(seed)
    
    # Preserve 13 LONG, 19 SHORT (based on exact assignment)
    directions = [o["direction"] for o in outcomes]
    
    count_greater_equal = 0
    
    for _ in range(iterations):
        shuffled_directions = directions[:]
        rng.shuffle(shuffled_directions)
        
        simulated_returns = []
        for i, o in enumerate(outcomes):
            direction = shuffled_directions[i]
            entry = o["entry_price"]
            exit_p = o["exit_price"]
            
            if direction == "LONG":
                gross = exit_p / entry - 1.0
            else:
                gross = entry / exit_p - 1.0
                
            net = gross - 2 * friction_bps / 10000.0
            simulated_returns.append(net)
            
        sim_mean = sum(simulated_returns) / len(simulated_returns)
        if sim_mean >= actual_mean:
            count_greater_equal += 1
            
    p_value = (count_greater_equal + 1) / (iterations + 1)
    
    return {
        "iterations": iterations,
        "count_greater_equal_actual": count_greater_equal,
        "empirical_p_value": p_value
    }

def chronological_concentration_control(returns: List[float], iterations: int, seed: int, friction_bps: float, actual_max_dd: float, actual_max_lose_streak: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    
    dd_greater = 0
    streak_greater = 0
    
    for _ in range(iterations):
        shuffled = returns[:]
        rng.shuffle(shuffled)
        
        sim_metrics = calculate_metrics(shuffled)
        
        if sim_metrics["maximum_drawdown"] >= actual_max_dd:
            dd_greater += 1
        if sim_metrics["longest_losing_streak"] >= actual_max_lose_streak:
            streak_greater += 1
            
    p_dd = (dd_greater + 1) / (iterations + 1)
    p_streak = (streak_greater + 1) / (iterations + 1)
    
    return {
        "iterations": iterations,
        "empirical_p_value_max_drawdown": p_dd,
        "empirical_p_value_longest_losing_streak": p_streak
    }
