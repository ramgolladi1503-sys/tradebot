import pandas as pd
import numpy as np

class ModelHealth:
    def __init__(self, threshold_accuracy=0.55, window=50):
        """
        threshold_accuracy: below this accuracy, retrain ML model
        window: number of recent trades to check
        """
        self.threshold = threshold_accuracy
        self.window = window

    def check_model_performance(self, trade_history_df: pd.DataFrame):
        """
        trade_history_df columns: ['pl', 'predicted', 'actual']
        Returns True if retraining needed
        """
        recent = trade_history_df.tail(self.window)
        if recent.empty:
            return False

        accuracy = (recent['predicted'] == recent['actual']).mean()
        print(f"[ModelHealth] Recent Accuracy: {accuracy:.2f}")

        if accuracy < self.threshold:
            print("[ModelHealth] Accuracy below threshold. Retraining needed.")
            return True
        return False

