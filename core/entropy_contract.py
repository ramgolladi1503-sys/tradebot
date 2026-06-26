import math
from typing import Dict, List, Optional

def shannon_entropy(probabilities: Dict[str, float], base: str = "e") -> float:
    """Calculate the Shannon entropy of a probability distribution."""
    if not probabilities:
        return 0.0
    
    validate_probability_vector(probabilities)
    
    entropy = 0.0
    for p in probabilities.values():
        if p > 0:
            if base == "e":
                entropy -= p * math.log(p)
            elif base == "2":
                entropy -= p * math.log2(p)
            elif base == "10":
                entropy -= p * math.log10(p)
            else:
                raise ValueError("Unsupported base. Use 'e', '2', or '10'.")
    return entropy

def max_entropy(num_states: int, base: str = "e") -> float:
    """Calculate the maximum theoretical entropy for a given number of states."""
    if num_states <= 0:
        return 0.0
        
    if base == "e":
        return math.log(num_states)
    elif base == "2":
        return math.log2(num_states)
    elif base == "10":
        return math.log10(num_states)
    else:
        raise ValueError("Unsupported base. Use 'e', '2', or '10'.")

def normalized_entropy(probabilities: Dict[str, float], base: str = "e") -> float:
    """Calculate the normalized entropy (entropy / max_entropy) scaled to [0, 1]."""
    num_states = len(probabilities)
    if num_states <= 1:
        return 0.0
        
    entropy = shannon_entropy(probabilities, base=base)
    max_ent = max_entropy(num_states, base=base)
    
    if max_ent == 0.0:
        return 0.0
        
    normalized = entropy / max_ent
    return min(max(normalized, 0.0), 1.0)

def validate_probability_vector(probabilities: Dict[str, float], tolerance: float = 1e-6) -> None:
    """Validate that the probability vector represents a valid probability distribution."""
    if not probabilities:
        return
        
    total_prob = 0.0
    for key, p in probabilities.items():
        if not math.isfinite(p):
            raise ValueError(f"Probability for {key} is not a finite number: {p}")
        if p < 0.0:
            raise ValueError(f"Probability for {key} is negative: {p}")
        total_prob += p
        
    if not math.isclose(total_prob, 1.0, abs_tol=tolerance):
        raise ValueError(f"Probabilities must sum to 1.0, but sum is {total_prob}")

def entropy_diagnostics(probabilities: Dict[str, float], labels: Optional[List[str]] = None) -> Dict[str, float]:
    """Calculate comprehensive entropy diagnostics for logging and thresholding."""
    if not probabilities:
        return {
            "entropy": 0.0,
            "normalized_entropy": 0.0,
            "max_entropy": 0.0,
            "num_states": 0
        }
        
    # If explicit labels are provided, pad missing probabilities with 0.0
    if labels:
        full_probs = {label: probabilities.get(label, 0.0) for label in labels}
    else:
        full_probs = probabilities

    entropy = shannon_entropy(full_probs)
    num_states = len(full_probs)
    max_ent = max_entropy(num_states)
    norm_ent = normalized_entropy(full_probs)

    if entropy > max_ent + 1e-6:
        raise ValueError(f"Calculated entropy {entropy} exceeds theoretical maximum {max_ent}")

    return {
        "entropy": entropy,
        "normalized_entropy": norm_ent,
        "max_entropy": max_ent,
        "num_states": num_states
    }
