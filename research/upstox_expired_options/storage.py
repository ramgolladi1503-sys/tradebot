import os
import shutil
from pathlib import Path
import pandas as pd

def atomic_write_parquet(df: pd.DataFrame, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")
    df.to_parquet(tmp_path, index=False)
    # atomic rename
    os.rename(tmp_path, out_path)\n