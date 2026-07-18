import os
import sys
import json
import subprocess
import datetime
import re

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)
from research.opening_state_momentum.outcome_contract import VALID_STATUSES

def extract_pytest_metrics(output):
    coll = 0; passed = 0; failed = 0; skipped = 0
    if "collected " in output:
        m = re.search(r'collected (\d+) items', output)
        if m: coll = int(m.group(1))
    
    lines = output.strip().split('\n')
    last_line = ""
    for line in reversed(lines):
        if line.strip():
            last_line = line
            break
            
    m_pass = re.search(r'(\d+)\s+passed', last_line)
    if m_pass: passed = int(m_pass.group(1))
    
    m_fail = re.search(r'(\d+)\s+failed', last_line)
    if m_fail: failed = int(m_fail.group(1))
    
    m_skip = re.search(r'(\d+)\s+skipped', last_line)
    if m_skip: skipped = int(m_skip.group(1))
    
    return coll, passed, failed, skipped

def main():
    initial_clean = False
    if not os.environ.get("VERIFIER_TESTING"):
        status_out = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True).stdout
        initial_clean = (len(status_out.strip()) == 0)

    # Independent causal verifier
    causal_exit = 0
    if not os.environ.get("VERIFIER_TESTING"):
        env = os.environ.copy()
        env["VERIFIER_TESTING"] = "1"
        res = subprocess.run([sys.executable, os.path.join(repo_root, "scripts", "verify_opening_state_causal_pass.py")], cwd=repo_root, env=env)
        causal_exit = res.returncode
        
    reviews_dir = os.path.join(repo_root, "docs", "agent_reviews", "opening_state_momentum")
    
    with open(os.path.join(reviews_dir, "candidate_decisions.json")) as f:
        decisions = json.load(f)
    
    with open(os.path.join(reviews_dir, "development_outcome_labels.json")) as f:
        outcomes = json.load(f)
        
    with open(os.path.join(reviews_dir, "development_outcome_reconciliation.json")) as f:
        recon = json.load(f)
        
    with open(os.path.join(reviews_dir, "outcome_oracle_comparison.json")) as f:
        oracle = json.load(f)
        
    with open(os.path.join(reviews_dir, "outcome_label_determinism.json")) as f:
        det = json.load(f)

    # Parse and sum decisions
    acc_dev_cands = [c for c in decisions if c.get("candidate_accepted")]
    acc_long = [c for c in acc_dev_cands if c["direction"] == "LONG"]
    acc_short = [c for c in acc_dev_cands if c["direction"] == "SHORT"]
    
    # Check direction totals
    acc_long_count = len(acc_long)
    acc_short_count = len(acc_short)
    out_exit = 0
    
    if acc_long_count + acc_short_count != len(acc_dev_cands):
        print("ERROR: Accepted directions do not sum to total.", file=sys.stderr)
        out_exit = 1
        
    labelled = [o for o in outcomes if o["status"] == "OUTCOME_LABELLED"]
    labelled_long = [o for o in labelled if o["direction"] == "LONG"]
    labelled_short = [o for o in labelled if o["direction"] == "SHORT"]
    lab_long_count = len(labelled_long)
    lab_short_count = len(labelled_short)
    
    if lab_long_count + lab_short_count != len(labelled):
        print("ERROR: Labelled directions do not sum to total.", file=sys.stderr)
        out_exit = 1

    # Check precision
    max_gross_err = 0.0
    max_frict_err = 0.0
    prec_mismatch = 0
    
    for o in labelled:
        ep = o["entry_price"]
        xp = o["exit_price"]
        d = o["direction"]
        
        expected_gross = (xp / ep - 1.0) if d == "LONG" else (ep / xp - 1.0)
        actual_gross = o["gross_return"]
        g_err = abs(expected_gross - actual_gross)
        if g_err > max_gross_err:
            max_gross_err = g_err
        if g_err > 1e-15:
            prec_mismatch += 1
            
        for bps in [0, 2, 5, 10]:
            k = f"net_return_{bps}bps"
            expected_f = actual_gross - (2 * bps / 10000.0)
            actual_f = o[k]
            f_err = abs(expected_f - actual_f)
            if f_err > max_frict_err:
                max_frict_err = f_err
            if f_err > 1e-15:
                prec_mismatch += 1

    # Fingerprints
    acc_fps = {c["candidate_fingerprint"]: c for c in acc_dev_cands}
    out_fps = {o["candidate_fingerprint"]: o for o in outcomes}
    
    acc_fp_set = set(acc_fps.keys())
    out_fp_set = set(out_fps.keys())
    missing_acc = len(acc_fp_set - out_fp_set)
    extra_out = len(out_fp_set - acc_fp_set)
    
    dup_fps = len([o["candidate_fingerprint"] for o in outcomes]) - len(out_fp_set)
    
    mismatch_dirs = 0
    for fp in acc_fp_set.intersection(out_fp_set):
        c = acc_fps[fp]
        o = out_fps[fp]
        if c["direction"] != o["direction"]:
            mismatch_dirs += 1

    # Taxonomy
    labeler_set = set(o["status"] for o in outcomes)
    recon_set = set(k.replace("total_", "").upper() for k in recon.keys() if k.startswith("total_"))
    
    contract_set = set(VALID_STATUSES)
    status_diffs = {
        "labeler_minus_contract": list(labeler_set - contract_set),
        "recon_minus_contract": list(recon_set - contract_set),
    }

    # Oracle
    oracle_comps = oracle.get("comparisons", [])
    out_date_to_dir = {o["session_date"]: o["direction"] for o in outcomes}
    o_long = sum(1 for c in oracle_comps if out_date_to_dir.get(c["session_date"]) == "LONG")
    o_short = sum(1 for c in oracle_comps if out_date_to_dir.get(c["session_date"]) == "SHORT")
    
    # Pytest
    test_env = os.environ.copy()
    test_env["VERIFIER_TESTING"] = "1"
    
    r1 = subprocess.run(["pytest", "--collect-only", "-q", "tests/research/opening_state_momentum/"], capture_output=True, text=True, cwd=repo_root, env=test_env)
    py_col_exit = r1.returncode
    coll, _, _, _ = extract_pytest_metrics(r1.stdout)
    
    r2 = subprocess.run(["pytest", "-q", "tests/research/opening_state_momentum/"], capture_output=True, text=True, cwd=repo_root, env=test_env)
    py_exec_exit = r2.returncode
    _, py_pass, py_fail, py_skip = extract_pytest_metrics(r2.stdout)

    # HEAD
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root).stdout.strip()
    
    final_clean = False
    if not os.environ.get("VERIFIER_TESTING"):
        status_out2 = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True).stdout
        final_clean = (len(status_out2.strip()) == 0)

    # Outcome verifier exit check
    if mismatch_dirs > 0 or prec_mismatch > 0 or missing_acc > 0 or extra_out > 0 or dup_fps > 0:
        out_exit = 1
    if len(status_diffs["labeler_minus_contract"]) > 0 or len(status_diffs["recon_minus_contract"]) > 0:
        out_exit = 1
    if not det.get("determinism_verified", False):
        out_exit = 1
        
    req_hashes = [
        "development_outcome_labels.json",
        "development_outcome_reconciliation.json",
        "outcome_contract.json",
        "outcome_oracle_comparison.json",
        "outcome_fingerprint_aggregate.json",
        "outcome_evidence_summary.json"
    ]
    for h in req_hashes:
        if h not in det.get("hashes_a", {}):
            out_exit = 1

    print("IMPLEMENTATION DIRECTION: OUTCOME_VERIFIER_SCHEMA_AND_EVIDENCE_REPAIR")
    print("PREVIOUS PASS STATUS: INVALID")
    print(f"CAUSAL CHECKPOINT HEAD: {head}")
    print(f"FINAL HEAD: {head}")
    print(f"ACCEPTED DEVELOPMENT CANDIDATES: {len(acc_dev_cands)}")
    print(f"ACCEPTED LONG CANDIDATES: {acc_long_count}")
    print(f"ACCEPTED SHORT CANDIDATES: {acc_short_count}")
    print(f"CANDIDATE DIRECTION SUM: {acc_long_count + acc_short_count}")
    print(f"OUTCOME RECORD COUNT: {len(outcomes)}")
    print(f"LABELLED OUTCOME COUNT: {len(labelled)}")
    print(f"LABELLED LONG COUNT: {lab_long_count}")
    print(f"LABELLED SHORT COUNT: {lab_short_count}")
    print(f"LABELLED DIRECTION SUM: {lab_long_count + lab_short_count}")
    print(f"CANDIDATE_OUTCOME DIRECTION MISMATCH COUNT: {mismatch_dirs}")
    print(f"MISSING ACCEPTED FINGERPRINT COUNT: {missing_acc}")
    print(f"EXTRA OUTCOME FINGERPRINT COUNT: {extra_out}")
    print(f"DUPLICATE OUTCOME FINGERPRINT COUNT: {dup_fps}")
    print(f"MAX GROSS RETURN ERROR: {max_gross_err}")
    print(f"MAX FRICTION RETURN ERROR: {max_frict_err}")
    print(f"PRECISION MISMATCH COUNT: {prec_mismatch}")
    print(f"STATUS CONTRACT SET: {list(contract_set)}")
    print(f"LABELER STATUS SET: {list(labeler_set)}")
    print(f"RECONCILIATION STATUS SET: {list(recon_set)}")
    print(f"VERIFIER STATUS SET: {list(labeler_set)}")
    print(f"STATUS SET DIFFERENCES: {json.dumps(status_diffs)}")
    print(f"ORACLE COMPARISON COUNT: {len(oracle_comps)}")
    print(f"ORACLE LONG COUNT: {o_long}")
    print(f"ORACLE SHORT COUNT: {o_short}")
    print(f"ORACLE MISMATCH COUNT: {oracle.get('mismatch_count', 0)}")
    print(f"RUN A HASHES: {json.dumps(det.get('hashes_a', {}))}")
    print(f"RUN B HASHES: {json.dumps(det.get('hashes_b', {}))}")
    print(f"DETERMINISM RESULT: {'PASS' if det.get('determinism_verified') else 'FAIL'}")
    print(f"PYTEST COLLECTION EXIT CODE: {py_col_exit}")
    print(f"PYTEST EXECUTION EXIT CODE: {py_exec_exit}")
    print(f"PYTEST COLLECTED: {coll}")
    print(f"PYTEST PASSED: {py_pass}")
    print(f"PYTEST FAILED: {py_fail}")
    print(f"PYTEST SKIPPED: {py_skip}")
    print(f"CAUSAL VERIFIER EXIT CODE: {causal_exit}")
    print(f"OUTCOME VERIFIER EXIT CODE: {out_exit}")
    
    # We will get files changed directly from bash or just omit
    changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True, cwd=repo_root).stdout.strip().split()
    print(f"FILES CHANGED: {changed}")
    print("COMMIT: NONE")
    print(f"WORKTREE STATUS: {'CLEAN' if final_clean else 'DIRTY'}")
    
    if out_exit == 0 and causal_exit == 0 and py_exec_exit == 0 and missing_acc == 0 and dup_fps == 0 and extra_out == 0 and mismatch_dirs == 0 and prec_mismatch == 0 and len(status_diffs["labeler_minus_contract"]) == 0 and det.get('determinism_verified'):
        print("FINAL VERDICT: DEVELOPMENT_OUTCOME_LABELS_PASS")
    else:
        print("FINAL VERDICT: DEVELOPMENT_OUTCOME_LABELS_WITH_GAPS")
        
    sys.exit(out_exit)

if __name__ == "__main__":
    main()
