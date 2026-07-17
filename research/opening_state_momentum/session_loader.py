import json
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
from typing import List, Dict, Any, Tuple

class ManifestMismatchError(Exception):
    pass

class Loader:
    def __init__(self, manifest_path: str, expected_portable_hash: str):
        self.manifest_path = Path(manifest_path)
        with open(self.manifest_path) as f:
            self.manifest_data = json.load(f)
            
        actual_hash = self.manifest_data.get("portable_dataset_hash")
        if actual_hash != expected_portable_hash:
            raise ManifestMismatchError(f"DATASET_MANIFEST_MISMATCH: Expected hash {expected_portable_hash}, got {actual_hash}")
            
        # Extract files from candidate_replay_underlying_candles group
        # Sort by relative path to guarantee order
        self.files = sorted(self.manifest_data.get("stable_files", []), key=lambda x: x.get("relative_path"))
        
        # Deduplicate content aliases by preferring the first absolute path per sha256
        seen_shas = set()
        self.eligible_files = []
        for f in self.files:
            if f.get("data_family") == "underlying_candles":
                sha = f.get("sha256")
                if sha not in seen_shas:
                    seen_shas.add(sha)
                    self.eligible_files.append(f)

    def load_session_data(self, file_record: Dict[str, Any]) -> Tuple[pd.DataFrame, List[str]]:
        path = Path(file_record["absolute_path"])
        if not path.exists():
            return pd.DataFrame(), ["FILE_NOT_FOUND"]
            
        try:
            pf = pq.ParquetFile(path)
            schema_names = pf.schema.to_arrow_schema().names
            cols = ["timestamp", "open", "high", "low", "close", "volume", "symbol"]
            available_cols = [c for c in cols if c in schema_names]
            
            df = pf.read(columns=available_cols).to_pandas()
            if df.empty:
                return pd.DataFrame(), ["EMPTY_FILE"]
                
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            # Normalize timezone
            if df["timestamp"].dt.tz is None:
                # Naive localization based on IST contract
                df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")
            else:
                df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata")
                
            return df, []
        except Exception as e:
            return pd.DataFrame(), [f"LOAD_ERROR: {str(e)}"]
