# live_nifty_gpt_bot_v4.py
import os
import time
import pandas as pd
from kiteconnect import KiteConnect
import openai
from dotenv import load_dotenv
import re

# ------------------- LOAD ENV VARIABLES -------------------
load_dotenv()

KITE_API_KEY = os.getenv("KITE_API_KEY")
KITE_API_SECRET = os.getenv("KITE_API_SECRET")
KITE_USER_ID = os.getenv("KITE_USER_ID")
KITE_PASSWORD = os.getenv("KITE_PASSWORD")  # optional if using 2FA flow
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SYMBOL = "NIFTY"
TOP_N_OI = 5
REFRESH_INTERVAL = 60  # seconds

# ------------------- INIT OPENAI -------------------
openai.api_key = OPENAI_API_KEY

# ------------------- KITE SESSION MANAGEMENT -------------------
def generate_access_token():
    kite = KiteConnect(api_key=KITE_API_KEY)
    print("Generating new access token...")
    
    # Note: You need to open the login URL manually and get request_token
    # For full automation, you need 2FA bypass flow (Zerodha doesn't allow fully headless login)
    login_url = kite.login_url()
    print("Login URL (open in browser and get request_token):", login_url)
    request_token = input("Enter the request_token from login URL: ").strip()
    
    data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
    access_token = data["access_token"]
    print("New access_token generated.")
    return access_token

def get_kite_client(access_token):
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(access_token)
    return kite

# ------------------- FETCH & PROCESS DATA -------------------
def fetch_option_chain(kite, symbol=SYMBOL):
    instruments = kite.instruments("NSE")
    df = pd.DataFrame(instruments)
    if 'tradingsymbol' in df.columns:
        df = df[df['tradingsymbol'].str.contains(symbol)]
        df = df[df['tradingsymbol'].str.contains("CE|PE", regex=True)]
    else:
        return pd.DataFrame()
    return df

def get_live_quotes(kite, symbols):
    if not symbols:
        return pd.DataFrame()
    try:
        quotes = kite.ltp(symbols)
        df = pd.DataFrame.from_dict(quotes, orient='index')
        return df
    except Exception as e:
        print("Error fetching live quotes:", e)
        return pd.DataFrame()

def filter_top_oi(df, top_n=TOP_N_OI):
    if df.empty or 'oi' not in df.columns:
        return df
    df_ce = df[df['tradingsymbol'].str.contains("CE")].copy()
    df_pe = df[df['tradingsymbol'].str.contains("PE")].copy()
    top_ce = df_ce.sort_values('oi', ascending=False).head(top_n)
    top_pe = df_pe.sort_values('oi', ascending=False).head(top_n)
    return pd.concat([top_ce, top_pe])

def format_for_gpt(live_data):
    if live_data.empty:
        return "No live data available."
    summary = ""
    for idx, row in live_data.iterrows():
        ltp = row.get('last_price', 'NA')
        oi = row.get('oi', 'NA')
        iv = row.get('implied_volatility', 'NA')
        type_ = "CE" if "CE" in idx else "PE"
        summary += f"{idx} | Type: {type_} | LTP: {ltp} | OI: {oi} | IV: {iv}\n"
    return summary

def get_gpt_analysis(formatted_text):
    if not formatted_text or formatted_text == "No live data available.":
        return "No data sent to GPT for analysis."
    
    prompt = (
        formatted_text +
        "\n\nProvide trading suggestions with columns: Strike | Type | Stop Loss | Target | Strategy | Recommendation"
    )

    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are an expert NIFTY options analyst."},
            {"role": "user", "content": prompt}
        ]
    )
    return response['choices'][0]['message']['content']

def parse_gpt_table(gpt_text):
    lines = gpt_text.strip().split("\n")
    table_data = []
    for line in lines:
        if re.match(r"Strike\s*\|", line, re.I):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 6:
            table_data.append(parts)
    if table_data:
        df = pd.DataFrame(table_data, columns=["Strike", "Type", "Stop Loss", "Target", "Strategy", "Recommendation"])
        df["Highlight"] = df["Recommendation"].apply(lambda x: "✅" if "buy" in x.lower() or "long" in x.lower() else "")
        return df
    return pd.DataFrame()

# ------------------- MAIN LOOP -------------------
def main():
    access_token = generate_access_token()
    kite = get_kite_client(access_token)

    while True:
        print("\nFetching NIFTY option chain...")
        option_chain = fetch_option_chain(kite)
        if option_chain.empty:
            print("No options found. Skipping this interval.")
            time.sleep(REFRESH_INTERVAL)
            continue

        top_options = filter_top_oi(option_chain)
        symbols = top_options['tradingsymbol'].tolist()
        live_data = get_live_quotes(kite, symbols)

        formatted_text = format_for_gpt(live_data)
        print("Formatted Data Sent to GPT:\n", formatted_text)

        gpt_analysis = get_gpt_analysis(formatted_text)
        print("\nGPT Raw Table:\n", gpt_analysis)

        df_trades = parse_gpt_table(gpt_analysis)
        if not df_trades.empty:
            print("\n--- Ready-to-Trade Table ---\n")
            print(df_trades)
        else:
            print("\nNo trades parsed from GPT.")

        print(f"\nWaiting {REFRESH_INTERVAL} seconds for next update...\n")
        time.sleep(REFRESH_INTERVAL)

# ------------------- RUN -------------------
if __name__ == "__main__":
    main()

