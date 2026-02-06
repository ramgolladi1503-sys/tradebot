import os
import pandas as pd
from core.feature_builder import add_indicators

def build_dataset_from_ohlc(csv_path, horizon=5, threshold=0.001):
    """
    Build a ML dataset from OHLCV data.
    Creates two samples per row: call (is_call=1) and put (is_call=0).
    Label = 1 if future move in direction >= threshold.
    """
    df = pd.read_csv(csv_path)
    df = add_indicators(df)
    df = df.dropna().reset_index(drop=True)

    rows = []
    for i in range(len(df) - horizon):
        row = df.iloc[i]
        future = df.iloc[i + horizon]
        future_return = (future["close"] / row["close"]) - 1

        base = {
            "ltp": row["close"],
            "bid": row["close"] * 0.999,
            "ask": row["close"] * 1.001,
            "spread_pct": 0.002,
            "volume": row["volume"],
            "atr": row.get("atr_14", 0),
            "vwap_dist": (row["close"] - row["vwap"]) / row["vwap"] if row.get("vwap", 0) else 0,
            "moneyness": 0.0,
            "vwap_slope": row.get("vwap_slope", 0),
            "rsi_mom": row.get("rsi_mom", 0),
            "vol_z": row.get("vol_z", 0)
        }

        # Call sample
        label_call = 1 if future_return >= threshold else 0
        rows.append({**base, "is_call": 1, "target": label_call})

        # Put sample
        label_put = 1 if (-future_return) >= threshold else 0
        rows.append({**base, "is_call": 0, "target": label_put})

    return pd.DataFrame(rows)

def build_dataset_from_folder(data_dir, output_path=None, horizon=5, threshold=0.001):
    all_parts = []
    for fname in os.listdir(data_dir):
        if not fname.endswith(".csv"):
            continue
        if "_" not in fname:
            continue
        part = build_dataset_from_ohlc(os.path.join(data_dir, fname), horizon=horizon, threshold=threshold)
        part["source_file"] = fname
        all_parts.append(part)

    if not all_parts:
        return None

    dataset = pd.concat(all_parts, ignore_index=True)
    if output_path:
        dataset.to_csv(output_path, index=False)
    return dataset
