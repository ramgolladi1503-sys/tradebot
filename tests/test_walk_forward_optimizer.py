import pytest
from core.analytics.walk_forward_optimizer import generate_walk_forward_splits

def test_generate_walk_forward_splits_basic():
    data = list(range(10))
    # IS: 4, OOS: 2, Step: 2
    splits = generate_walk_forward_splits(data, in_sample_size=4, out_of_sample_size=2, step_size=2)
    
    assert splits != []
    assert splits[0] == ([0, 1, 2, 3], [4, 5])
    assert splits[1] == ([2, 3, 4, 5], [6, 7])
    assert splits[2] == ([4, 5, 6, 7], [8, 9])

def test_generate_walk_forward_splits_exact_fit():
    data = list(range(6))
    splits = generate_walk_forward_splits(data, in_sample_size=4, out_of_sample_size=2, step_size=2)
    assert splits != []
    assert splits[0] == ([0, 1, 2, 3], [4, 5])

def test_generate_walk_forward_splits_not_enough_data():
    data = list(range(5))
    splits = generate_walk_forward_splits(data, in_sample_size=4, out_of_sample_size=2, step_size=2)
    assert splits == []
