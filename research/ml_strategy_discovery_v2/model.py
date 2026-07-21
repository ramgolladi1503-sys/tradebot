import pandas as pd
from typing import Dict, Any, List
from sklearn.tree import DecisionTreeClassifier
import hashlib
import json

def rule_mask(df: pd.DataFrame, candidate: Dict[str, Any]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for cond in candidate.get("conditions", []):
        if cond["operator"] == ">":
            mask &= (df[cond["feature"]] > cond["threshold"])
        elif cond["operator"] == "<=":
            mask &= (df[cond["feature"]] <= cond["threshold"])
    return mask

def _hash_conditions(conditions: List[Dict[str, Any]]) -> str:
    # Sort for deterministic hashing of equivalent rules
    sorted_conds = sorted(conditions, key=lambda x: f"{x['feature']}{x['operator']}{x['threshold']}")
    return hashlib.sha256(json.dumps(sorted_conds, sort_keys=True).encode("utf-8")).hexdigest()

def generate_candidates(df: pd.DataFrame, features: List[str], target_col: str = "label_return_r", max_depth: int = 3, min_samples_leaf: int = 50, seed: int = 42) -> List[Dict[str, Any]]:
    # Generate candidates with deterministic behavior
    y = (df[target_col] > 0).astype(int)
    X = df[features].fillna(0)
    
    clf = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=min_samples_leaf, random_state=seed)
    clf.fit(X, y)
    
    tree = clf.tree_
    candidates = []
    seen_hashes = set()
    
    def traverse(node_id, current_rule):
        if tree.children_left[node_id] == tree.children_right[node_id]:
            # Leaf node
            if tree.value[node_id][0][1] > tree.value[node_id][0][0]:
                c_hash = _hash_conditions(current_rule)
                if c_hash not in seen_hashes:
                    seen_hashes.add(c_hash)
                    candidates.append({"conditions": list(current_rule), "rule_hash": c_hash})
            return
            
        feature = features[tree.feature[node_id]]
        # deterministic threshold rounding to 4 decimal places
        threshold = round(float(tree.threshold[node_id]), 4)
        
        # Left child (<=)
        left_rule = list(current_rule)
        left_rule.append({"feature": feature, "operator": "<=", "threshold": threshold})
        traverse(tree.children_left[node_id], left_rule)
        
        # Right child (>)
        right_rule = list(current_rule)
        right_rule.append({"feature": feature, "operator": ">", "threshold": threshold})
        traverse(tree.children_right[node_id], right_rule)

    traverse(0, [])
    return candidates
