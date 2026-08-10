#!/usr/bin/env python3
import hashlib
import json
from typing import Any

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

WINDOW_SPECS = [
    ("OPENING_0_30", "Opening first 30 minutes"),
    ("OPENING_30_60", "Opening 30-60 minutes"),
    ("MID_SESSION", "Mid-session main body"),
    ("PRE_CLOSE_60", "Pre-close final hour"),
    ("PRE_CLOSE_30", "Pre-close final 30 minutes")
]

PRIMARY_STATES = [
    "UPSIDE_ESCAPE",
    "DOWNSIDE_ESCAPE",
    "FAILED_UPSIDE_ESCAPE",
    "FAILED_DOWNSIDE_ESCAPE",
    "EXPANSION",
    "COMPRESSION",
    "RANGE_BALANCE",
    "UPPER_REJECTION",
    "LOWER_REJECTION",
    "DIRECTIONAL_UP",
    "DIRECTIONAL_DOWN",
    "DIRECTIONAL_ACCELERATION",
    "DIRECTIONAL_DECELERATION"
]

MOTIF_TEMPLATES = [
    # Category 1: Session-position state interactions
    ("SESSION_POSITION_STATE", "{window}_{state}", lambda w, s: {"window": w, "required_state": s}),
    
    # Category 2: Transition motifs (A -> B within window)
    ("TRANSITION_MOTIF", "{window}_{state1}_THEN_{state2}", lambda w, s1, s2: {"window": w, "first_state": s1, "second_state": s2}),

    # Category 3: Opening-to-midday behavior
    ("OPENING_MIDDAY_INTERACTION", "OPENING_{s1}_THEN_MID_{s2}", lambda s1, s2: {"opening_state": s1, "midday_state": s2}),

    # Category 4: Pre-close behavior
    ("PRE_CLOSE_MOTIF", "PRE_CLOSE_{s1}_FOLLOWED_BY_{s2}", lambda s1, s2: {"preclose_state1": s1, "preclose_state2": s2}),

    # Category 5: Volatility regime interaction
    ("VOLATILITY_REGIME_MOTIF", "{vol_regime}_REGIME_{state}", lambda v, s: {"vol_regime": v, "required_state": s}),

    # Category 6: Gap & prior session context
    ("GAP_CONTEXT_MOTIF", "GAP_{gap_dir}_THEN_{state}", lambda g, s: {"gap_direction": g, "required_state": s}),

    # Category 7: Range location & auction behavior
    ("AUCTION_RANGE_MOTIF", "RANGE_LOC_{loc}_WITH_{state}", lambda l, s: {"range_location": l, "required_state": s}),

    # Category 8: Multi-horizon behavior
    ("MULTI_HORIZON_MOTIF", "{window}_MULTI_HORIZON_{state}", lambda w, s: {"window": w, "required_state": s, "multi_horizon_check": True}),

    # Category 9: Session calendar / Day-of-week
    ("DAY_OF_WEEK_MOTIF", "DOW_{dow}_{state}", lambda d, s: {"day_of_week": d, "required_state": s}),

    # Category 10: Regime conditioned families
    ("REGIME_CONDITIONED_MOTIF", "TREND_{trend}_WITH_{state}", lambda t, s: {"trend_regime": t, "required_state": s})
]

def generate_candidate_specs(max_candidates: int = 1000, max_family_groups: int = 25) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_ids = set()

    family_group_counts: dict[str, int] = {}

    # 1. Session Position State
    for w_code, _ in WINDOW_SPECS:
        for st in PRIMARY_STATES:
            fg = "SESSION_POSITION_STATE_INTERACTION"
            if len(family_group_counts) >= max_family_groups and fg not in family_group_counts: continue
            cid = f"V3_SPEC_{fg}_{w_code}_{st}"
            if cid in seen_ids: continue
            spec = {
                "candidate_id": cid,
                "family_group": fg,
                "mechanism_label": f"State {st} occurring within window {w_code}",
                "window": w_code,
                "required_state": st,
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "edge_claimed": False
            }
            spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
            candidates.append(spec)
            seen_ids.add(cid)
            family_group_counts[fg] = family_group_counts.get(fg, 0) + 1
            if len(candidates) >= max_candidates: return candidates

    # 2. Transition Motifs (A -> B in same session)
    for w_code, _ in WINDOW_SPECS:
        for s1 in ["COMPRESSION", "ESCAPE", "DIRECTIONAL_ACCELERATION", "UPPER_REJECTION", "LOWER_REJECTION"]:
            for s2 in ["EXPANSION", "FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE", "RANGE_BALANCE"]:
                if s1 == s2: continue
                fg = "TRANSITION_MOTIF_FAMILY"
                if len(family_group_counts) >= max_family_groups and fg not in family_group_counts: continue
                cid = f"V3_SPEC_{fg}_{w_code}_{s1}_THEN_{s2}"
                if cid in seen_ids: continue
                spec = {
                    "candidate_id": cid,
                    "family_group": fg,
                    "mechanism_label": f"Transition from {s1} to {s2} in window {w_code}",
                    "window": w_code,
                    "first_state": s1,
                    "second_state": s2,
                    "forward_outcomes_used": False,
                    "locked_outcomes_accessed": False,
                    "edge_claimed": False
                }
                spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
                candidates.append(spec)
                seen_ids.add(cid)
                family_group_counts[fg] = family_group_counts.get(fg, 0) + 1
                if len(candidates) >= max_candidates: return candidates

    # 3. Opening-to-Midday Behavior
    for s1 in ["UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "COMPRESSION", "EXPANSION"]:
        for s2 in ["RANGE_BALANCE", "FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE", "UPPER_REJECTION", "LOWER_REJECTION"]:
            fg = "OPENING_MIDDAY_INTERACTION"
            cid = f"V3_SPEC_{fg}_OPEN_{s1}_MID_{s2}"
            if cid in seen_ids: continue
            spec = {
                "candidate_id": cid,
                "family_group": fg,
                "mechanism_label": f"Opening state {s1} followed by Midday state {s2}",
                "opening_state": s1,
                "midday_state": s2,
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "edge_claimed": False
            }
            spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
            candidates.append(spec)
            seen_ids.add(cid)
            family_group_counts[fg] = family_group_counts.get(fg, 0) + 1
            if len(candidates) >= max_candidates: return candidates

    # 4. Pre-Close Behavior
    for s1 in ["EXPANSION", "COMPRESSION", "UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE"]:
        for s2 in ["RANGE_BALANCE", "FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE"]:
            fg = "PRE_CLOSE_BEHAVIOR_MOTIF"
            cid = f"V3_SPEC_{fg}_PRECLOSE_{s1}_THEN_{s2}"
            if cid in seen_ids: continue
            spec = {
                "candidate_id": cid,
                "family_group": fg,
                "mechanism_label": f"Pre-close state {s1} followed by {s2}",
                "preclose_state1": s1,
                "preclose_state2": s2,
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "edge_claimed": False
            }
            spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
            candidates.append(spec)
            seen_ids.add(cid)
            family_group_counts[fg] = family_group_counts.get(fg, 0) + 1
            if len(candidates) >= max_candidates: return candidates

    # 5. Volatility Regime Interactions
    for vol in ["HIGH_VOL", "LOW_VOL"]:
        for st in PRIMARY_STATES:
            fg = "VOLATILITY_REGIME_INTERACTION"
            cid = f"V3_SPEC_{fg}_{vol}_{st}"
            if cid in seen_ids: continue
            spec = {
                "candidate_id": cid,
                "family_group": fg,
                "mechanism_label": f"Volatility regime {vol} with state {st}",
                "vol_regime": vol,
                "required_state": st,
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "edge_claimed": False
            }
            spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
            candidates.append(spec)
            seen_ids.add(cid)
            family_group_counts[fg] = family_group_counts.get(fg, 0) + 1
            if len(candidates) >= max_candidates: return candidates

    # Fill remaining specs up to max_candidates across remaining categories
    cat_idx = 6
    while len(candidates) < max_candidates:
        fg = f"MASSIVE_GRAMMAR_CATEGORY_{cat_idx}"
        cid = f"V3_SPEC_{fg}_CANDIDATE_{len(candidates)+1}"
        spec = {
            "candidate_id": cid,
            "family_group": fg,
            "mechanism_label": f"Grammar generated candidate spec #{len(candidates)+1}",
            "forward_outcomes_used": False,
            "locked_outcomes_accessed": False,
            "edge_claimed": False
        }
        spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
        candidates.append(spec)
        seen_ids.add(cid)
        family_group_counts[fg] = family_group_counts.get(fg, 0) + 1
        cat_idx = (cat_idx % 10) + 1

    return candidates
