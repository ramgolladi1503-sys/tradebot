import numpy as np

from core.tf_utils import configure_tensorflow
configure_tensorflow()

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Input

def build_microstructure_model(input_dim):
    model = Sequential(
        [
            Input(shape=(input_dim,)),
            Dense(64, activation="relu"),
            Dropout(0.2),
            Dense(32, activation="relu"),
            Dense(1, activation="sigmoid"),
        ]
    )
    model.compile(
        optimizer="adam",
        loss="binary_crossentropy",
        metrics=["accuracy"],
    )
    return model

def prepare_microstructure_features(df, return_names=False):
    candidates = [
        ["return_1", "volume_delta", "oi_delta", "depth_imbalance", "depth_spread_pct"],
        ["spread_pct", "volume", "oi_change"],
        ["return_1", "volume_delta", "oi_delta"],
        ["return_1", "volume", "oi"],
    ]
    cols = None
    for cset in candidates:
        if all(c in df.columns for c in cset):
            cols = cset
            break
    if cols is None:
        # fallback: use all numeric columns
        cols = [c for c in df.columns if df[c].dtype != "object"]
    # add cross-asset features when available
    cross_cols = [c for c in ["fx_ret_5m", "vix_z", "crude_ret_15m", "corr_fx_nifty"] if c in df.columns]
    for c in cross_cols:
        if c not in cols:
            cols.append(c)
    X = df[cols].fillna(0).values
    if return_names:
        return X, cols
    return X
