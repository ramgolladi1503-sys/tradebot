import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, precision_score
import xgboost as xgb
import warnings

warnings.filterwarnings("ignore")


def train_ml_overlay():
    print("Loading OOS trades dataset...")
    from pathlib import Path

    df = pd.read_csv(Path() / "data" / "oos_trades.csv")

    # 1. Feature Engineering & Labels
    # We want to predict if a trade will be profitable (pl > 0)
    df["label"] = (df["pl"] > 0).astype(int)

    # Select our statistical features extracted from vectorized_signals
    features = [
        "rsi_14",
        "adx_14",
        "vwap_slope",
        "trend_dist",
        "atr_pct",
        "hour",
        "minute",
    ]

    # Drop rows with NaNs in features
    df = df.dropna(subset=features)

    X = df[features]
    y = df["label"]

    print(f"Total valid trades for ML: {len(X)}")
    print(f"Baseline Win Rate: {y.mean() * 100:.2f}%\n")

    # 2. Train-Test Split (Chronological to prevent data leakage)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, shuffle=False
    )

    # 3. Train XGBoost Classifier
    print("Training XGBoost Classifier...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        random_state=42,
        eval_metric="logloss",
    )

    model.fit(X_train, y_train)

    # 4. Predict Probabilities on Holdout Test Set
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    print("\n--- ML Overlay Performance on Holdout Set ---")

    # Test different probability thresholds
    thresholds = [0.5, 0.6, 0.7, 0.75, 0.8]

    for thresh in thresholds:
        # Model authorizes trade only if probability > thresh
        authorized_trades = y_pred_proba > thresh

        if authorized_trades.sum() == 0:
            print(f"Threshold > {thresh}: 0 trades authorized.")
            continue

        actual_wins = y_test[authorized_trades].sum()
        total_authorized = authorized_trades.sum()
        precision = actual_wins / total_authorized * 100

        print(f"Threshold > {thresh}:")
        print(f"  Authorized Trades: {total_authorized} (out of {len(y_test)} total)")
        print(f"  Resulting Win Rate: {precision:.2f}%")

        if precision >= 70:
            print(f"  *** 70%+ WIN RATE ACHIEVED AT THRESHOLD {thresh}! ***")
        print()

    print("\nSaving trained model to models/xgb_overlay.json...")
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    model.save_model(models_dir / "xgb_overlay.json")
    print("Model saved successfully.")


if __name__ == "__main__":
    train_ml_overlay()
