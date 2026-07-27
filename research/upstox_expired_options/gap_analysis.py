import os
import json
import pandas as pd
from datetime import timedelta

EVIDENCE_ROOT = "/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1"
UNDERLYING_PATH = "/Users/madhuram/tradebot/runtime/indices/aggregated_bars.parquet"

def get_previous_thursday(expiry_date):
    # NIFTY expiries are Thursday. Previous cycle end is previous Thursday.
    # The new cycle starts on Friday.
    # We want the Friday open as the selection timestamp.
    # expiry_date is a datetime.date
    # weekday(): Monday=0, Thursday=3, Friday=4
    # If expiry is Thursday, previous Friday is expiry - 6 days.
    return expiry_date - timedelta(days=6)

def build_gap_analysis():
    inventory_path = os.path.join(EVIDENCE_ROOT, "manifests", "pre_resume_inventory.parquet")
    if not os.path.exists(inventory_path):
        print("Inventory not found.")
        return
        
    df_inv = pd.read_parquet(inventory_path)
    
    underlying_available = os.path.exists(UNDERLYING_PATH)
    if underlying_available:
        df_nifty = pd.read_parquet(UNDERLYING_PATH)
        df_nifty = df_nifty[df_nifty['symbol'] == 'NIFTY'].copy()
        df_nifty['timestamp'] = pd.to_datetime(df_nifty['timestamp'])
        df_nifty = df_nifty.set_index('timestamp').sort_index()
    else:
        df_nifty = None
        
    expiries = df_inv['expiry'].unique()
    
    gap_records = []
    atm_ledger = []
    
    for exp_str in sorted(expiries):
        exp_date = pd.to_datetime(exp_str).date()
        cycle_start_date = get_previous_thursday(exp_date)
        
        # Target selection timestamp: cycle_start_date at 09:15:00 Asia/Kolkata
        target_ts = pd.Timestamp(f"{cycle_start_date} 09:15:00", tz="Asia/Kolkata")
        
        # Check if we have underlying data
        underlying_price = None
        selection_ts = None
        
        if df_nifty is not None:
            # Find the first available bar on or after target_ts, but BEFORE expiry
            expiry_end_ts = pd.Timestamp(f"{exp_date} 15:30:00", tz="Asia/Kolkata")
            slice_df = df_nifty[(df_nifty.index >= target_ts) & (df_nifty.index <= expiry_end_ts)]
            
            if not slice_df.empty:
                selection_ts = slice_df.index[0]
                underlying_price = slice_df.iloc[0]['open']
                
        # Determine actual available contract strikes from contracts.json
        raw_dir = os.path.join(EVIDENCE_ROOT, "raw", "responses", "NIFTY", f"expiry={exp_str}")
        contracts_file = os.path.join(raw_dir, "contracts.json")
        available_strikes = set()
        if os.path.exists(contracts_file):
            with open(contracts_file, "r") as f:
                c_data = json.load(f)
            for c in c_data:
                available_strikes.add(float(c["strike_price"]))
                
        atm_strike = None
        selected_strikes = []
        if underlying_price is not None:
            # Round to nearest 50. Tie-break: round up.
            rem = underlying_price % 50
            if rem >= 25:
                atm_strike = underlying_price + (50 - rem)
            else:
                atm_strike = underlying_price - rem
                
            selected_strikes = [
                atm_strike - 100,
                atm_strike - 50,
                atm_strike,
                atm_strike + 50,
                atm_strike + 100
            ]
            
            # Filter selected strikes by what is actually available in the exchange grid
            if available_strikes:
                selected_strikes = [s for s in selected_strikes if s in available_strikes]
                
        # Analyze current inventory for this expiry
        sub = df_inv[df_inv['expiry'] == exp_str]
        attempted = len(sub[sub['status'] != 'NO_CONTRACT_REQUESTS'])
        valid = len(sub[sub['status'] == 'VALID_COMPLETE'])
        empty = len(sub[sub['status'] == 'EMPTY_RESPONSE'])
        
        expected_count = len(selected_strikes) * 2 # CE and PE
        
        # Check previously attempted strikes
        prev_strikes = set(sub[sub['status'] != 'NO_CONTRACT_REQUESTS']['strike'].dropna())
        
        gap_reason = "COMPLETE_FOR_POLICY" if valid == expected_count and expected_count > 0 else "UNRESOLVED"
        
        if underlying_price is None:
            gap_reason = "MISSING_UNDERLYING_REFERENCE"
        elif attempted == 0:
            gap_reason = "NO_CONTRACT_REQUESTS"
        elif empty == attempted and attempted > 0:
            gap_reason = "ALL_REQUESTS_EMPTY"
            if set(selected_strikes) != prev_strikes:
                gap_reason = "INVALID_ATM_SELECTION"
        elif valid < expected_count:
            gap_reason = "PARTIAL_FOR_POLICY"
            if not set(selected_strikes).issubset(prev_strikes):
                gap_reason = "INVALID_ATM_SELECTION"
                
        repair_action = "FETCH_MISSING" if gap_reason != "COMPLETE_FOR_POLICY" else "NONE"
        if gap_reason == "MISSING_UNDERLYING_REFERENCE":
            repair_action = "BLOCK_UNTIL_UNDERLYING_AVAILABLE"
            
        gap_records.append({
            'expiry': exp_str,
            'underlying_reference_available': underlying_price is not None,
            'underlying_reference_source': UNDERLYING_PATH if underlying_price else None,
            'selection_timestamp': str(selection_ts) if selection_ts else None,
            'underlying_price': underlying_price,
            'available_contract_count': len(available_strikes) * 2,
            'available_strike_grid': str(sorted(list(available_strikes))),
            'selected_atm': atm_strike,
            'selected_strikes': str(selected_strikes),
            'expected_contract_count': expected_count,
            'attempted_contract_count': attempted,
            'populated_contract_count': valid,
            'empty_contract_count': empty,
            'missing_contract_count': expected_count - valid,
            'gap_reason': gap_reason,
            'repair_action': repair_action
        })
        
        if underlying_price is not None:
            atm_ledger.append({
                'expiry': exp_str,
                'selection_timestamp': str(selection_ts),
                'underlying_price': underlying_price,
                'strike_interval': 50.0,
                'available_strike_grid_hash': hash(tuple(sorted(list(available_strikes)))),
                'atm_strike': atm_strike,
                'selected_strikes': str(selected_strikes),
                'option_types': "['CE', 'PE']",
                'tie_break_rule': 'round_half_up',
                'underlying_source_path': UNDERLYING_PATH,
                'underlying_source_hash': "TODO",
                'selection_policy_version': "v1_bounded_atm_2"
            })
            
    df_gaps = pd.DataFrame(gap_records)
    df_atm = pd.DataFrame(atm_ledger)
    
    manifests_dir = os.path.join(EVIDENCE_ROOT, "manifests")
    df_atm.to_parquet(os.path.join(manifests_dir, "atm_selection_ledger.parquet"), index=False)
    df_gaps.to_parquet(os.path.join(manifests_dir, "gap_analysis.parquet"), index=False)
    
    # Save a gap report
    reports_dir = os.path.join(EVIDENCE_ROOT, "reports")
    out_md = os.path.join(reports_dir, "gap_analysis_report.md")
    with open(out_md, 'w') as f:
        f.write("# Gap Analysis Report\n\n")
        f.write(df_gaps[['expiry', 'gap_reason', 'repair_action', 'missing_contract_count']].to_markdown(index=False))
        
    print(f"Done. Ledger: {os.path.join(manifests_dir, 'atm_selection_ledger.parquet')}, Report: {out_md}")

if __name__ == "__main__":
    build_gap_analysis()
