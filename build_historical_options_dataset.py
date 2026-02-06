from kiteconnect import KiteConnect
import pandas as pd
import numpy as np
from datetime import datetime
import pickle
from credentials import API_KEY

# -----------------------------
# Kite Connect Setup
# -----------------------------
kite = KiteConnect(api_key=API_KEY)
with open("kite_access_token.pkl","rb") as f:
    kite.set_access_token(pickle.load(f))

# -----------------------------
# Parameters
# -----------------------------
START_DATE = "2023-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")
CSV_FILE = "../data/processed_options_features_historical_full.csv"

# -----------------------------
# Helper functions
# -----------------------------
def black_scholes_delta(S, K, T, r, sigma, option_type="CE"):
    from scipy.stats import norm
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T)/(sigma*np.sqrt(T))
    if option_type=="CE":
        return norm.cdf(d1)
    else:
        return norm.cdf(d1)-1

def black_scholes_vega(S, K, T, r, sigma):
    from scipy.stats import norm
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T)/(sigma*np.sqrt(T))
    return S * norm.pdf(d1) * np.sqrt(T)

def detect_regime(df):
    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["ATR_14"] = df["High"] - df["Low"]
    latest = df.iloc[-1]
    if latest["Close"] > latest["SMA_50"]:
        return "TRENDING"
    elif latest["ATR_14"] > df["ATR_14"].rolling(20).mean().iloc[-1]*1.5:
        return "VOLATILE"
    else:
        return "RANGING"

# -----------------------------
# Feature engineering
# -----------------------------
def compute_technical_indicators(df):
    df["SMA_10"] = df["Close"].rolling(10).mean()
    df["EMA_20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["RSI_14"] = df["Close"].diff().rolling(14).apply(lambda x: (x[x>0].sum()/14))
    df["ATR_14"] = df["High"] - df["Low"]
    return df

def compute_option_features(df):
    # Returns
    df["Return_1"] = df["Close"].pct_change()
    df["Days_to_Expiry"] = 30  # placeholder, can be dynamic if expiry info available
    df["Moneyness"] = df["Close"]/df["Close"].rolling(20).mean()
    
    # Greeks
    S = df["Close"]
    K = df["Close"].rolling(20).mean()
    T = df["Days_to_Expiry"]/252
    r = 0.07
    sigma = df["Close"].pct_change().rolling(20).std() * np.sqrt(252)
    
    df["Delta"] = black_scholes_delta(S, K, T, r, sigma)
    df["Vega"] = black_scholes_vega(S, K, T, r, sigma)
    
    # Target
    df["Target"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
    
    # Regime
    df["Regime"] = detect_regime(df)
    
    return df

# -----------------------------
# Build dataset
# -----------------------------
def build_dataset():
    # For now, read historical OHLC CSV (can replace with kite historical API fetch)
    df = pd.read_csv(CSV_FILE)
    
    df = compute_technical_indicators(df)
    df = compute_option_features(df)
    
    # Drop NaNs
    df.dropna(inplace=True)
    
    # Scale/normalize features for ML
    features = ["SMA_10","EMA_20","RSI_14","ATR_14","Return_1","Delta","Vega","Days_to_Expiry","Moneyness"]
    for f in features:
        df[f] = (df[f] - df[f].mean()) / (df[f].std()+1e-6)
    
    df.to_csv(CSV_FILE, index=False)
    print(f"✅ Dataset with Delta/Vega/Regime saved to {CSV_FILE}")

# -----------------------------
# Main
# -----------------------------
if __name__=="__main__":
    build_dataset()

