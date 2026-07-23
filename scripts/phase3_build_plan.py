import json
from pathlib import Path
from datetime import datetime, timedelta

def get_last_n_trading_days(n=7):
    # Rough estimation: skip weekends.
    # Today is the start point (2026-07-23 approx)
    days = []
    current = datetime.now()
    while len(days) < n:
        if current.weekday() < 5:  # 0-4 are Mon-Fri
            days.append(current.strftime("%Y-%m-%d"))
        current -= timedelta(days=1)
    return days

def main():
    reports_dir = Path("runtime/constituent_lead_lag/upstox_v1/reports")
    manifests_dir = Path("runtime/constituent_lead_lag/upstox_v1/manifests")
    manifests_dir.mkdir(parents=True, exist_ok=True)
    
    with open(reports_dir / "instrument_resolution.json", "r") as f:
        instruments = json.load(f)
        
    trading_days = get_last_n_trading_days(7)
    start_date = trading_days[-1]
    end_date = trading_days[0]
    
    plan = []
    
    for inst in instruments:
        plan.append({
            "symbol": inst["symbol"],
            "instrument_key": inst["upstox_instrument_key"],
            "start_date": start_date,
            "end_date": end_date,
            "interval": "5minute",
            "status": "PENDING"
        })
        
    with open(manifests_dir / "historical_fetch_plan.json", "w") as f:
        json.dump(plan, f, indent=2)
        
    print(f"Created fetch plan for {len(plan)} instruments from {start_date} to {end_date}.")

if __name__ == "__main__":
    main()
