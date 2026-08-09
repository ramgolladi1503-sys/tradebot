#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

POLICY_DEFAULT = "research/strategy_certification/CAMPAIGN_V2_DATA_ADMISSION_POLICY.json"
OUT_DEFAULT = "research/evidence/strategy_certification/CAMPAIGN_V2_DATA_ADMISSION_RESULT.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def norm(x: str) -> str:
    return x.strip().lower()


def load_columns(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as h:
            r = csv.reader(h)
            return [norm(x) for x in next(r)]
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as h:
            for line in h:
                if line.strip():
                    x = json.loads(line)
                    if not isinstance(x, dict):
                        raise ValueError("jsonl_first_record_not_object")
                    return [norm(k) for k in x]
        raise ValueError("dataset_empty")
    if suffix == ".json":
        x = read_json(path)
        if isinstance(x, list) and x and isinstance(x[0], dict):
            return [norm(k) for k in x[0]]
        raise ValueError("json_dataset_requires_nonempty_array_of_objects")
    if suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
        except Exception as e:
            raise ValueError(f"parquet_requires_pyarrow:{e}")
        return [norm(x) for x in pq.ParquetFile(path).schema.names]
    raise ValueError(f"unsupported_dataset_type:{suffix}")


def manifest_complete(m: dict[str, Any], required: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    mapping = {
        "dataset_sha256_required": "dataset_sha256",
        "source_name_required": "source_name",
        "source_path_or_vendor_reference_required": "source_path_or_vendor_reference",
        "timezone_required": "timezone",
        "timestamp_semantics_required": "timestamp_semantics",
        "field_semantics_required": "field_semantics",
        "date_range_required": ("date_start", "date_end"),
        "row_count_required": "row_count",
    }
    for flag, field in mapping.items():
        if not required.get(flag):
            continue
        fields = field if isinstance(field, tuple) else (field,)
        for f in fields:
            v = m.get(f)
            if v is None or v == "" or v == {} or (f == "row_count" and int(v or 0) <= 0):
                missing.append(f)
    return missing


def inspect_quality(path: Path, cols: set[str], m: dict[str, Any]) -> dict[str, Any]:
    report = {
        "quality_scan_performed": False,
        "rows_scanned": 0,
        "duplicate_key_rows": None,
        "missingness_by_required_field": {},
        "crossed_or_inverted_bid_ask_rows": None,
        "zero_or_negative_price_rows": None,
        "invalid_option_domain_rows": None,
    }
    if path.suffix.lower() != ".csv":
        return report
    key_fields = [norm(x) for x in m.get("key_fields", []) if norm(x) in cols]
    required_scan = [x for x in ["timestamp", "bid", "ask", "expiry", "strike", "option_type"] if x in cols]
    seen = set(); dup = 0; crossed = 0; nonpositive = 0; invalid_domain = 0
    missing = {x: 0 for x in required_scan}
    with path.open("r", encoding="utf-8", newline="") as h:
        for row in csv.DictReader(h):
            report["rows_scanned"] += 1
            r = {norm(k): v for k, v in row.items()}
            for f in required_scan:
                if r.get(f, "").strip() == "": missing[f] += 1
            if key_fields:
                key = tuple(r.get(k, "") for k in key_fields)
                if key in seen: dup += 1
                else: seen.add(key)
            if "bid" in cols and "ask" in cols:
                try:
                    b = float(r.get("bid", "nan")); a = float(r.get("ask", "nan"))
                    if b > a: crossed += 1
                    if b <= 0 or a <= 0: nonpositive += 1
                except Exception:
                    pass
            if "strike" in cols:
                try:
                    if float(r.get("strike", "nan")) <= 0: invalid_domain += 1
                except Exception:
                    invalid_domain += 1
            if "option_type" in cols:
                ot = r.get("option_type", "").strip().upper()
                if ot and ot not in {"CE", "PE", "CALL", "PUT", "C", "P"}: invalid_domain += 1
    report.update({
        "quality_scan_performed": True,
        "duplicate_key_rows": dup if key_fields else None,
        "missingness_by_required_field": missing,
        "crossed_or_inverted_bid_ask_rows": crossed if {"bid", "ask"}.issubset(cols) else None,
        "zero_or_negative_price_rows": nonpositive if {"bid", "ask"}.issubset(cols) else None,
        "invalid_option_domain_rows": invalid_domain if ("strike" in cols or "option_type" in cols) else None,
    })
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--policy", default=POLICY_DEFAULT)
    ap.add_argument("--output", default=OUT_DEFAULT)
    a = ap.parse_args(argv)
    root = Path(a.repo_root).resolve(); mp = Path(a.manifest); pp = root / a.policy; out = root / a.output
    if not mp.is_absolute(): mp = root / mp
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "CAMPAIGN_V2_DATA_INSUFFICIENT_EVIDENCE",
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "campaign_v2_open_permitted": False,
    }
    try:
        policy = read_json(pp); manifest = read_json(mp)
        seal = read_json(root / policy["campaign_v1_seal_path"])
        if seal.get("status") != policy["campaign_v1_status_required"]:
            raise ValueError("campaign_v1_not_sealed_as_required")
        info = manifest.get("information_class")
        cls = policy["accepted_information_classes"].get(info)
        if cls is None:
            result.update(status="CAMPAIGN_V2_DATA_REJECTED", reasons=["INFORMATION_CLASS_NOT_ADMITTED"])
        else:
            dp = Path(str(manifest.get("dataset_path", "")))
            if not dp.is_absolute(): dp = root / dp
            if not dp.exists():
                result.update(status="CAMPAIGN_V2_DATA_INSUFFICIENT_EVIDENCE", reasons=["DATASET_PATH_MISSING"])
            else:
                actual_hash = sha256(dp); declared = str(manifest.get("dataset_sha256", ""))
                cols_list = load_columns(dp); cols = set(cols_list)
                reasons: list[str] = []
                if declared != actual_hash: reasons.append("DATASET_HASH_MISMATCH")
                missing_manifest = manifest_complete(manifest, policy["provenance_requirements"])
                if missing_manifest: reasons.append("MISSING_PROVENANCE_FIELDS:" + ",".join(sorted(missing_manifest)))
                if not any(norm(x) in cols for x in cls["required_any_identifier_fields"]): reasons.append("IDENTIFIER_FIELD_MISSING")
                for f in cls["required_fields"]:
                    if norm(f) not in cols: reasons.append("REQUIRED_FIELD_MISSING:" + norm(f))
                for f in cls.get("required_market_fields", []):
                    if norm(f) not in cols: reasons.append("REQUIRED_MARKET_FIELD_MISSING:" + norm(f))
                info_present = sorted({norm(x) for x in cls["required_information_fields_any"] if norm(x) in cols})
                if len(info_present) < int(cls["minimum_information_fields_present"]): reasons.append("INSUFFICIENT_NEW_INFORMATION_FIELDS")
                field_sem = {norm(k): str(v).strip() for k, v in (manifest.get("field_semantics") or {}).items()}
                if any(not field_sem.get(f, "") for f in ["timestamp"] if f in cols): reasons.append("TIMESTAMP_FIELD_SEMANTICS_MISSING")
                quality = inspect_quality(dp, cols, manifest)
                if int(manifest.get("row_count", 0) or 0) != int(quality.get("rows_scanned", manifest.get("row_count", 0)) or 0) and quality["quality_scan_performed"]:
                    reasons.append("ROW_COUNT_MISMATCH")
                hard_reject = any(x.startswith(("DATASET_HASH_MISMATCH", "REQUIRED_FIELD_MISSING", "REQUIRED_MARKET_FIELD_MISSING", "IDENTIFIER_FIELD_MISSING", "INSUFFICIENT_NEW_INFORMATION_FIELDS")) for x in reasons)
                status = "CAMPAIGN_V2_DATA_REJECTED" if hard_reject else ("CAMPAIGN_V2_DATA_INSUFFICIENT_EVIDENCE" if reasons else "CAMPAIGN_V2_DATA_ADMITTED")
                result.update({
                    "status": status,
                    "campaign_v2_open_permitted": status == "CAMPAIGN_V2_DATA_ADMITTED",
                    "information_class": info,
                    "manifest_sha256": sha256(mp),
                    "dataset_sha256": actual_hash,
                    "columns": cols_list,
                    "new_information_fields_present": info_present,
                    "reasons": reasons,
                    "quality_report": quality,
                    "interpretation": "Admission validates data-class/provenance/field capability only. It does not establish a trading edge or certify any strategy."
                })
    except Exception as e:
        result.update(status="CAMPAIGN_V2_DATA_INSUFFICIENT_EVIDENCE", reasons=[f"{type(e).__name__}:{e}"])
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "CAMPAIGN_V2_DATA_ADMITTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
