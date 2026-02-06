# ===============================
# OPTIONS TRADING BOT STARTER SKELETON
# ===============================

import pandas as pd
import numpy as np
import yfinance as yf
from xgboost import XGBClassifier
import ta
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score, confusion_matrix
import datetime

# -------------------------------
# 1. Fetch Underlying Data
# -------------------------------
def fetch_underlying(symbol="^NSEI", interval="15m", period="1y"):
    data = yf.download(symbol, interval=interval, period=period)
    data = data[['Open','High','Low','Close','Volume']]
    data.dropna(inplace=True)
    return data

# -------------------------------
# 2. Fetch Options Data
# -------------------------------
# Placeholder: replace with live API call
def fetch_options():
    options_data = pd.read_csv("nifty_options.csv")  # must include: Close, Strike, Expiry, CE/PE, IV, Delta, Theta, Vega
    options_data['Expiry'] = pd.to_datetime(options_data['Expiry'])
    return options_data

# -------------------------------
# 3. Feature Engineering
# -------------------------------
def generate_features(underlying, options_data):
    # --- Underlying features ---
    underlying['SMA_10'] = ta.trend.sma_indicator(underlying['Close'], 10)
    underlying['EMA_20'] = ta.trend.ema_indicator(underlying['Close'], 20)
    underlying['RSI_14'] = ta.momentum.rsi(underlying['Close'], 14)
    underlying['ATR_14'] = ta.volatility.average_true_range(underlying['High'], underlying['Low'], underlying['Close'], 14)
    underlying['Return_1'] = underlying['Close'].pct_change(1)
    
    # Merge underlying features into options
    options_data = options_data.merge(underlying, left_index=True, right_index=True, how='left')
    
    # --- Options features ---
    options_data['Moneyness'] = options_data['Close'] / options_data['Strike']
    options_data['Days_to_Expiry'] = (options_data['Expiry'] - options_data.index).dt.days
    options_data['Premium_Return'] = options_data['Close'].pct_change(1)
    
    # Drop missing values
    options_data.dropna(inplace=True)
    return options_data

# -------------------------------
# 4. Define Target
# -------------------------------
def define_target(df, threshold=0.005):
    df['Target'] = (df['Premium_Return'].shift(-1) > threshold).astype(int)
    df.dropna(inplace=True)
    return df

# -------------------------------
# 5. Split Data
# -------------------------------
def split_data(df, train_ratio=0.8):
    train_size = int(len(df) * train_ratio)
    train = df.iloc[:train_size]
    test = df.iloc[train_size:]
    X_train = train.drop(['Target'], axis=1)
    y_train = train['Target']
    X_test = test.drop(['Target'], axis=1)
    y_test = test['Target']
    return X_train, X_test, y_train, y_test, test

# -------------------------------
# 6. Train XGBoost Model
# -------------------------------
def train_model(X_train, y_train, X_test, y_test):
    model = XGBClassifier(
        max_depth=4,
        learning_rate=0.05,
        n_estimators=500,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], early_stopping_rounds=20, verbose=True)
    return model

# -------------------------------
# 7. Evaluate Model
# -------------------------------
def evaluate_model(model, X_test, y_test):
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    cm = confusion_matrix(y_test, y_pred)
    print("Accuracy:", accuracy)
    print("Confusion Matrix:\n", cm)
    return y_pred

# -------------------------------
# 8. Backtest / Capital Simulation
# -------------------------------
def backtest(test, y_pred, initial_capital=100000, risk_per_trade=0.05):
    capital = initial_capital
    capital_history = []

    for i in range(len(test)):
        if y_pred[i] == 1:  # buy
            position = capital * risk_per_trade / test['Close'].iloc[i]
        else:
            position = 0
        capital += position * (test['Close'].iloc[i] - test['Close'].shift(1).iloc[i])
        capital_history.append(capital)

    plt.plot(capital_history)
    plt.title("Backtested Capital Over Time")
    plt.show()
    return capital_history

# -------------------------------
# 9. Main Execution
# -------------------------------
def main():
    underlying = fetch_underlying()
    options_data = fetch_options()
    
    df = generate_features(underlying, options_data)
    df = define_target(df)
    
    X_train, X_test, y_train, y_test, test = split_data(df)
    
    model = train_model(X_train, y_train, X_test, y_test)
    
    y_pred = evaluate_model(model, X_test, y_test)
    
    backtest(test, y_pred)

if __name__ == "__main__":
    main()

