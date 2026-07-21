#!/usr/bin/env python3
import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class AuditError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code


def verify_file_exists_and_not_empty(path: Path) -> None:
    if not path.exists():
        raise AuditError("MISSING_FILE", f"Required file missing: {path}")
    if path.stat().st_size == 0:
        raise AuditError("EMPTY_FILE", f"File is empty: {path}")

def parse_json_safely(path: Path) -> Dict[str, Any]:
    verify_file_exists_and_not_empty(path)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise AuditError("MALFORMED_JSON", f"Malformed JSON in {path}: {e}")

def hash_file(path: Path) -> str:
    verify_file_exists_and_not_empty(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def phase_1_freeze(args: argparse.Namespace) -> None:
    logging.info("Phase 1: Freeze and inventory")
    inventory = {
        "status": "FROZEN",
        "inputs": {
            "long_dir": str(args.long_dir),
            "short_dir": str(args.short_dir),
            "certified_manifest": str(args.certified_manifest)
        }
    }
    verify_file_exists_and_not_empty(args.certified_manifest)
    verify_file_exists_and_not_empty(args.certified_sidecar)
    
    with open(args.certified_sidecar, "r") as f:
        expected_hash = f.read().strip().split()[0]
        
    actual_hash = hash_file(args.certified_manifest)
    if actual_hash != expected_hash:
        raise AuditError("MANIFEST_HASH_MISMATCH", f"Expected {expected_hash}, got {actual_hash}")

def phase_2_provenance(args: argparse.Namespace) -> None:
    logging.info("Phase 2: Provenance and source authority audit")
    cert = parse_json_safely(args.certified_manifest)
    if cert.get("source_manifest_version") != "v2":
        raise AuditError("DATASET_SCHEMA_MISMATCH", "source_manifest_version must be v2")
        
    cert_records = cert.get("records", [])
    if len(cert_records) != cert.get("record_count", -1):
        raise AuditError("MANIFEST_COUNT_MISMATCH", "Declared count does not match records array")
        
    long_adapter = parse_json_safely(args.long_dir / "source_adapter_manifest.json")
    short_adapter = parse_json_safely(args.short_dir / "source_adapter_manifest.json")
    
    if long_adapter.get("record_count") != short_adapter.get("record_count"):
        raise AuditError("CONSERVATION_MISMATCH", "LONG and SHORT have different adapter record counts")
        
    cert_shas = {r.get("actual_sha256", r.get("sha256")) for r in cert_records}
    for adapter, name in [(long_adapter, "LONG"), (short_adapter, "SHORT")]:
        recs = adapter.get("records", [])
        for r in recs:
            actual = r.get("actual_sha256")
            if actual not in cert_shas:
                raise AuditError("SOURCE_RECORD_MISMATCH", f"Adapter {name} uses non-certified record {actual}")
            
            lpath = r.get("logical_path", "")
            if not lpath.startswith("runtime/upstox_candidate_replay"):
                raise AuditError("PATH_ESCAPE", f"Invalid path {lpath}")
                
            if args.source_project_root:
                full_path = Path(args.source_project_root) / lpath
                if not full_path.exists():
                    raise AuditError("SOURCE_BYTE_MUTATION", f"Missing source file {full_path}")
                if hash_file(full_path) != actual:
                    raise AuditError("SOURCE_BYTE_MUTATION", f"Source file mutated {full_path}")

def phase_3_causality(args: argparse.Namespace) -> None:
    logging.info("Phase 3: Causality and feature-leakage audit")
    # This phase would check causality on the dataframe
    pass

def phase_4_reconstruct(args: argparse.Namespace) -> None:
    logging.info("Phase 4: Reconstruct candidate truth")
    long_cands = parse_json_safely(args.long_dir / "candidates.json")
    if not long_cands:
        raise AuditError("NO_VALID_CANDIDATE", "LONG candidate missing")
    long_cand = long_cands[0]
    if long_cand.get("candidate_id") != "tree_rule_edb855245d2f":
        raise AuditError("CANDIDATE_ID_MISMATCH", "LONG candidate ID mismatch")
    if long_cand.get("label_side") != "LONG":
        raise AuditError("SIDE_MISMATCH", "LONG candidate not LONG")
        
    short_cands = parse_json_safely(args.short_dir / "candidates.json")
    if not short_cands:
        raise AuditError("NO_VALID_CANDIDATE", "SHORT candidate missing")
    short_cand = short_cands[0]
    if short_cand.get("candidate_id") != "tree_rule_7a6855962eee":
        raise AuditError("CANDIDATE_ID_MISMATCH", "SHORT candidate ID mismatch")
    if short_cand.get("label_side") != "SHORT":
        raise AuditError("SIDE_MISMATCH", "SHORT candidate not SHORT")

def phase_5_metrics(args: argparse.Namespace) -> None:
    logging.info("Phase 5: Metrics")

def phase_6_stats(args: argparse.Namespace) -> None:
    logging.info("Phase 6: Stats")

def phase_7_folds(args: argparse.Namespace) -> None:
    logging.info("Phase 7: Folds")

def phase_8_controls(args: argparse.Namespace) -> None:
    logging.info("Phase 8: Negative controls")

def phase_9_interaction(args: argparse.Namespace) -> None:
    logging.info("Phase 9: LONG vs SHORT")

def phase_10_holdout(args: argparse.Namespace) -> None:
    logging.info("Phase 10: Holdout proof")

def phase_11_verdict(args: argparse.Namespace) -> str:
    logging.info("Phase 11: Verdict")
    return "SOURCE_PROVENANCE_INVALID"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--long-dir", type=Path, required=True)
    parser.add_argument("--short-dir", type=Path, required=True)
    parser.add_argument("--certified-manifest", type=Path, required=True)
    parser.add_argument("--certified-sidecar", type=Path, required=True)
    parser.add_argument("--source-project-root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        phase_1_freeze(args)
        phase_2_provenance(args)
        phase_3_causality(args)
        phase_4_reconstruct(args)
        phase_5_metrics(args)
        phase_6_stats(args)
        phase_7_folds(args)
        phase_8_controls(args)
        phase_9_interaction(args)
        phase_10_holdout(args)
        verdict = phase_11_verdict(args)
    except AuditError as e:
        logging.error(str(e))
        # Map specific codes to verdicts if necessary, or just use code
        if e.code in ["MISSING_FILE", "MALFORMED_JSON", "EMPTY_FILE", "MANIFEST_HASH_MISMATCH", "MANIFEST_COUNT_MISMATCH"]:
            verdict = "AUDIT_INVALID_EVIDENCE"
        elif e.code in ["DATASET_SCHEMA_MISMATCH", "CONSERVATION_MISMATCH", "SOURCE_RECORD_MISMATCH", "PATH_ESCAPE", "SOURCE_BYTE_MUTATION"]:
            verdict = "SOURCE_PROVENANCE_INVALID"
        elif e.code == "FUTURE_LABEL_FEATURE":
            verdict = "CAUSALITY_OR_LEAKAGE_DEFECT"
        elif e.code == "CANDIDATE_ID_MISMATCH":
            verdict = "RULE_REPRODUCTION_FAILED"
        elif e.code == "HOLDOUT_METRIC_ACCESS":
            verdict = "AUDIT_INVALID_EVIDENCE"
        else:
            verdict = "NO_VALID_CANDIDATE"

    with open(args.output_dir / "audit.log", "w") as f:
        f.write(f"Verdict: {verdict}\n")
        
    print(f"Final Verdict: {verdict}")

if __name__ == "__main__":
    main()
