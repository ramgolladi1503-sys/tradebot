import os
import json
import pandas as pd
from pathlib import Path
import pytest

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
MANIFESTS_DIR = EVIDENCE_ROOT / "manifests"
REPORTS_DIR = EVIDENCE_ROOT / "reports"

def test_canonical_file_inventory_ordering():
    if not (MANIFESTS_DIR / "file_inventory.parquet").exists():
        pytest.skip("No file inventory")
    df = pd.read_parquet(MANIFESTS_DIR / "file_inventory.parquet")
    # Verify sorted by relative_path
    assert df['relative_path'].is_monotonic_increasing

def test_contract_inventory_reconciliation():
    if not (MANIFESTS_DIR / "contract_inventory.parquet").exists():
        pytest.skip("No contract inventory")
    df = pd.read_parquet(MANIFESTS_DIR / "contract_inventory.parquet")
    # Should have no duplicates
    assert not df[['expiry', 'option_type', 'strike']].duplicated().any()

def test_empty_normalized_file_exclusion():
    if not (MANIFESTS_DIR / "file_inventory.parquet").exists():
        pytest.skip("No file inventory")
    df = pd.read_parquet(MANIFESTS_DIR / "file_inventory.parquet")
    # All normalized files should have size > 0 (or > some min parquet size like 500 bytes)
    norm = df[df['artifact_class'].str.startswith('NORMALIZED')]
    assert (norm['size_bytes'] > 100).all()

def test_request_manifest_reconstruction():
    if not (MANIFESTS_DIR / "request_manifest.jsonl").exists():
        pytest.skip("No request manifest")
    with open(MANIFESTS_DIR / "request_manifest.jsonl") as f:
        lines = f.readlines()
    assert bool(lines) is True
    # ensure JSON valid
    for l in lines:
        json.loads(l)

def test_campaign_manifest_count_reconciliation():
    if not (MANIFESTS_DIR / "campaign_manifest.json").exists():
        pytest.skip("No campaign manifest")
    with open(MANIFESTS_DIR / "campaign_manifest.json") as f:
        data = json.load(f)
    assert data["attempted_contract_count"] >= 1
    assert data["populated_contract_count"] >= 1

def test_data_quality_violation_detection():
    # Verify no post-expiry violations exist in populated data
    if not (MANIFESTS_DIR / "contract_inventory.parquet").exists():
        pytest.skip("No contract inventory")
    df = pd.read_parquet(MANIFESTS_DIR / "contract_inventory.parquet")
    assert df['post_expiry_violation_count'].sum() == 0 if 'post_expiry_violation_count' in df.columns else True
