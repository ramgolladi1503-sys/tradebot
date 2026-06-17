from __future__ import annotations

from typing import List, Tuple, Any

def generate_walk_forward_splits(
    data: List[Any],
    in_sample_size: int,
    out_of_sample_size: int,
    step_size: int
) -> List[Tuple[List[Any], List[Any]]]:
    """
    Generate In-Sample and Out-of-Sample data splits for walk-forward optimization.
    
    Args:
        data: A chronologically sorted list of data items (e.g., trading days).
        in_sample_size: The number of items to include in the in-sample (training/optimization) period.
        out_of_sample_size: The number of items to include in the out-of-sample (testing) period.
        step_size: How many items to move the window forward for each fold.
        
    Returns:
        A list of tuples, where each tuple contains (in_sample_data, out_of_sample_data).
    """
    splits = []
    total_length = len(data)
    
    start_idx = 0
    while True:
        is_end_idx = start_idx + in_sample_size
        oos_end_idx = is_end_idx + out_of_sample_size
        
        if is_end_idx > total_length or oos_end_idx > total_length:
            break
            
        in_sample = data[start_idx:is_end_idx]
        out_of_sample = data[is_end_idx:oos_end_idx]
        
        splits.append((in_sample, out_of_sample))
        
        start_idx += step_size
        
    return splits
