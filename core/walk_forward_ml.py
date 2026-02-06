import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score
from models.train_utils import train_model

def walk_forward_train_test(df, feature_cols, target_col="target", train_size=0.6, step=500, calibrate=True, top_k=9):
    """
    Walk-forward ML evaluation.
    Train on expanding window, test on next step.
    Returns metrics dataframe and last trained model.
    """
    n = len(df)
    start_train = int(n * train_size)
    metrics = []
    last_model = None

    for start in range(start_train, n - step, step):
        train_df = df.iloc[:start].copy()
        test_df = df.iloc[start:start + step].copy()

        model, used_features = train_model(
            train_df, feature_cols, target_col=target_col, calibrate=calibrate, top_k=top_k
        )
        last_model = model

        X_test = test_df[used_features]
        y_test = test_df[target_col]
        y_pred = model.predict(X_test)

        metrics.append({
            "train_rows": len(train_df),
            "test_rows": len(test_df),
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),
            "recall": recall_score(y_test, y_pred, zero_division=0),
            "features_used": ",".join(used_features)
        })

    return pd.DataFrame(metrics), last_model
