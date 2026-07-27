import os
import json
import pandas as pd
from pathlib import Path
import pytest
from research.upstox_expired_options.validation import is_contract_complete

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
MANIFESTS_DIR = EVIDENCE_ROOT / "manifests"

def test_resume_idempotence():
    # If a contract is fully populated, resume logic should skip it.
    if not (MANIFESTS_DIR / "contract_inventory.parquet").exists():
        pytest.skip("No contract inventory")
    
    df = pd.read_parquet(MANIFESTS_DIR / "contract_inventory.parquet")
    valid_contracts = df[df['final_status'] == 'VALID_COMPLETE']
    if len(valid_contracts) == 0:
        pytest.skip("No valid complete contracts to test resume idempotence")
        
    contract = valid_contracts.iloc[0]
    
    # Mocking the folder paths
    norm_1m_path = EVIDENCE_ROOT / str(contract['normalized_1m_path'])
    norm_5m_path = EVIDENCE_ROOT / str(contract['normalized_5m_path'])
    
    # is_contract_complete usually checks existence of both
    assert norm_1m_path.exists()
    assert norm_5m_path.exists()
    
    # Our logic should determine it's complete
    assert is_contract_complete(str(norm_1m_path), str(norm_5m_path)) == True

def test_resume_missing():
    # If 1m exists but not 5m, it is not complete
    assert is_contract_complete("/tmp/dummy_1m.parquet", None) == False
    assert is_contract_complete(None, "/tmp/dummy_5m.parquet") == False
    assert is_contract_complete(None, None) == False
