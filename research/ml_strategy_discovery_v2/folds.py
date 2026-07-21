import pandas as pd
import numpy as np
from typing import Any

def generate_nested_folds(df: pd.DataFrame, num_folds: int = 5) -> list[dict[str, Any]]:
    """
    Chronologically split DEVELOPMENT_V1 into folds for walk-forward evaluation.
    This strictly isolates validation from the development set so we can run CV.
    """
    sessions = sorted(df["session_date"].unique())
    chunks = np.array_split(np.array(sessions, dtype=object), num_folds)
    folds = []
    
    for i, chunk in enumerate(chunks, start=1):
        if not len(chunk):
            continue
        val_start = str(chunk[0])
        val_end = str(chunk[-1])
        
        # Purge/Embargo: Drop 1 session before and 1 session after the validation chunk
        train_sessions = sorted(set(sessions) - set(chunk))
        
        # Find adjacent sessions
        if chunk[0] in sessions:
            idx_start = sessions.index(chunk[0])
            if idx_start > 0:
                if sessions[idx_start - 1] in train_sessions:
                    train_sessions.remove(sessions[idx_start - 1])
                    
        if chunk[-1] in sessions:
            idx_end = sessions.index(chunk[-1])
            if idx_end < len(sessions) - 1:
                if sessions[idx_end + 1] in train_sessions:
                    train_sessions.remove(sessions[idx_end + 1])
        folds.append({
            "fold": i,
            "train_sessions": train_sessions,
            "val_sessions": list(chunk),
            "val_start": val_start,
            "val_end": val_end
        })
        
    return folds
