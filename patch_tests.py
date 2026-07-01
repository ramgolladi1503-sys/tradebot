import re

path = "tests/test_review_queue_live_entry.py"
with open(path, "r") as f:
    content = f.read()

# For test_execute_permission_stays_execute_when_aligned_and_high_confidence
content = re.sub(
    r'monkeypatch\.setattr\(review_queue, "gate_decision", lambda \*_args, \*\*_kwargs: \{"hard_pass": True, "hard_reasons": \[\], "soft_reasons": \[\], "final_confidence": 0\.91\}\)',
    'monkeypatch.setattr(review_queue, "evaluate_candidate_decision", lambda *args: {"decision_action": "EXECUTE", "decision_reason": "execute", "final_score": 0.91, "raw_score": 0.91, "candidate_class": "test"})\n    monkeypatch.setattr(review_queue, "gate_decision", lambda *_args, **_kwargs: {"hard_pass": True, "hard_reasons": [], "soft_reasons": [], "final_confidence": 0.91})',
    content
)

# For test_execute_permission_soft_conf_reject_records_downgrade_provenance
content = re.sub(
    r'monkeypatch\.setattr\(\s*review_queue,\s*"gate_decision",\s*lambda \*_args, \*\*_kwargs: \{\s*"hard_pass": True,\s*"hard_reasons": \[\],\s*"soft_reasons": \[\],\s*"final_confidence": 0\.25,\s*},\s*\)',
    'monkeypatch.setattr(review_queue, "evaluate_candidate_decision", lambda *args: {"decision_action": "QUEUE", "decision_reason": "queue", "final_score": 0.25, "raw_score": 0.25, "candidate_class": "test"})\n        monkeypatch.setattr(review_queue, "gate_decision", lambda *_args, **_kwargs: {"hard_pass": True, "hard_reasons": [], "soft_reasons": [], "final_confidence": 0.25})',
    content
)

# For test_ready_status_preserves_raw_planning_for_executable_row
content = re.sub(
    r'monkeypatch\.setattr\(\s*review_queue,\s*"gate_decision",\s*lambda \*_args, \*\*_kwargs: \{\s*"hard_pass": True,\s*"hard_reasons": \[\],\s*"soft_reasons": \[\],\s*"final_confidence": 0\.92,\s*},\s*\)',
    'monkeypatch.setattr(review_queue, "evaluate_candidate_decision", lambda *args: {"decision_action": "EXECUTE", "decision_reason": "execute", "final_score": 0.92, "raw_score": 0.92, "candidate_class": "test"})\n        monkeypatch.setattr(review_queue, "gate_decision", lambda *_args, **_kwargs: {"hard_pass": True, "hard_reasons": [], "soft_reasons": [], "final_confidence": 0.92})',
    content
)

with open(path, "w") as f:
    f.write(content)
