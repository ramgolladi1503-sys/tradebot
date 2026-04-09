def should_replace(current_score,new_score,min_abs_delta=0.12,min_rel=0.2):
    if current_score is None:
        return True
    if new_score-current_score < min_abs_delta:
        return False
    if new_score < current_score*(1+min_rel):
        return False
    return True
