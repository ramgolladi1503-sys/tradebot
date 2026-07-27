import os
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
MANIFESTS_DIR = EVIDENCE_ROOT / "manifests"

def get_thursday_before(dt_date):
    days_to_subtract = (dt_date.weekday() - 3) % 7
    if days_to_subtract == 0:
        days_to_subtract = 7
    return dt_date - timedelta(days=days_to_subtract)

def main():
    print("Running Phase 2 Contract Inventory...")
    
    file_inv_path = MANIFESTS_DIR / "file_inventory.parquet"
    if not file_inv_path.exists():
        print("Missing file_inventory.parquet")
        return
        
    df_files = pd.read_parquet(file_inv_path)
    
    atm_ledger_path = MANIFESTS_DIR / "atm_selection_ledger.parquet"
    if not atm_ledger_path.exists():
        print("Missing atm_selection_ledger.parquet")
        return
        
    df_atm = pd.read_parquet(atm_ledger_path)
    # The ledger gives us target contracts
    # Expected columns in df_atm: expiry, strike, option_type, status, etc.
    # Actually, df_atm has exactly the wings we intended to fetch.
    
    # We will build contract records from the ledger, but also we must include any contract that actually exists in files
    # just in case there are orphans not in the ledger.
    
    contracts = {}
    
    # Pre-populate from atm_ledger
    for _, row in df_atm.iterrows():
        exp = row['expiry']
        val = row['selected_strikes']
        
        strikes = []
        if isinstance(val, (list, tuple)):
            strikes = val
        elif isinstance(val, str):
            import ast
            try:
                strikes = ast.literal_eval(val)
            except:
                pass
                
        # we expect CE and PE for each strike
        for st in strikes:
            st_int = int(float(st)) # handle '26150.0' -> 26150
            for opt in ['CE', 'PE']:
                key = (exp, opt, str(st_int))
                contracts[key] = {
                    'underlying': 'NIFTY',
                    'underlying_key': 'NSE_INDEX|Nifty 50',
                    'expiry': exp,
                    'strike': str(st_int),
                    'option_type': opt,
                    'trading_symbol': None,
                    'expired_instrument_key': None,
                    'exchange_token': None,
                    'lot_size': None,
                    'minimum_lot': None,
                    'weekly': None,
                    'raw_contract_metadata_path': None,
                    'raw_contract_metadata_sha256': None,
                    'raw_candle_path': None,
                    'raw_candle_sha256': None,
                    'normalized_1m_path': None,
                    'normalized_1m_sha256': None,
                    'normalized_5m_path': None,
                    'normalized_5m_sha256': None,
                    'request_from_date': None,
                    'request_to_date': None,
                    'one_minute_row_count': 0,
                    'five_minute_row_count': 0,
                    'first_candle': None,
                    'last_candle': None,
                    'unique_session_count': 0,
                    'empty_response': False,
                    'quarantined_row_count': 0,
                    'final_status': 'UNRESOLVED',
                    'status_reason': None
                }
                
    # Also add any files that exist but were not in ledger (orphans)
    unique_contracts = df_files[['expiry', 'option_type', 'strike']].dropna().drop_duplicates()
    
    for _, row in unique_contracts.iterrows():
        try:
            st = str(int(float(row['strike'])))
        except:
            st = str(row['strike'])
        key = (row['expiry'], row['option_type'], st)
        if key not in contracts:
            contracts[key] = {
                'underlying': 'NIFTY',
                'underlying_key': 'NSE_INDEX|Nifty 50',
                'expiry': row['expiry'],
                'strike': st,
                'option_type': row['option_type'],
                'trading_symbol': None,
                'expired_instrument_key': None,
                'exchange_token': None,
                'lot_size': None,
                'minimum_lot': None,
                'weekly': None,
                'raw_contract_metadata_path': None,
                'raw_contract_metadata_sha256': None,
                'raw_candle_path': None,
                'raw_candle_sha256': None,
                'normalized_1m_path': None,
                'normalized_1m_sha256': None,
                'normalized_5m_path': None,
                'normalized_5m_sha256': None,
                'request_from_date': None,
                'request_to_date': None,
                'one_minute_row_count': 0,
                'five_minute_row_count': 0,
                'first_candle': None,
                'last_candle': None,
                'unique_session_count': 0,
                'empty_response': False,
                'quarantined_row_count': 0,
                'final_status': 'UNRESOLVED',
                'status_reason': None
            }

    # Map inst_key to metadata
    inst_map = {}
    import json
    for _, row in df_files[df_files['artifact_class'] == 'RAW_CONTRACT_INVENTORY'].iterrows():
        try:
            path = EVIDENCE_ROOT / str(row['relative_path'])
            with open(path) as f:
                data = json.load(f)
                for item in data:
                    inst = item.get('instrument_key')
                    if inst:
                        inst_safe = inst.replace("|", "_")
                        st = str(int(float(item['strike_price'])))
                        inst_map[inst_safe] = (item['expiry'], item['instrument_type'], st)
        except:
            pass

    # Now populate from file_inventory
    # Group files by contract
    for _, f in df_files.iterrows():
        rp = str(f['relative_path'])
        expiry = f['expiry']
        option_type = f['option_type']
        strike = f['strike']
        
        if f['artifact_class'] == 'RAW_CANDLE_RESPONSE':
            inst_key = None
            for part in rp.split('/'):
                if part.startswith("instrument="):
                    inst_key = part.split("=")[1]
            if inst_key and inst_key in inst_map:
                expiry, option_type, strike = inst_map[inst_key]
                
        if not expiry or not option_type or not strike:
            continue
            
        try:
            st = str(int(float(strike)))
        except:
            st = str(strike)
            
        key = (expiry, option_type, st)
        if key not in contracts:
            contracts[key] = {
                'underlying': 'NIFTY',
                'underlying_key': 'NSE_INDEX|Nifty 50',
                'expiry': expiry,
                'strike': st,
                'option_type': option_type,
                'trading_symbol': None,
                'expired_instrument_key': None,
                'exchange_token': None,
                'lot_size': None,
                'minimum_lot': None,
                'weekly': None,
                'raw_contract_metadata_path': None,
                'raw_contract_metadata_sha256': None,
                'raw_candle_path': None,
                'raw_candle_sha256': None,
                'normalized_1m_path': None,
                'normalized_1m_sha256': None,
                'normalized_5m_path': None,
                'normalized_5m_sha256': None,
                'request_from_date': None,
                'request_to_date': None,
                'one_minute_row_count': 0,
                'five_minute_row_count': 0,
                'first_candle': None,
                'last_candle': None,
                'unique_session_count': 0,
                'empty_response': False,
                'quarantined_row_count': 0,
                'final_status': 'UNRESOLVED',
                'status_reason': None
            }
            
        c = contracts[key]
        
        c['trading_symbol'] = c['trading_symbol'] or f['trading_symbol']
        c['expired_instrument_key'] = c['expired_instrument_key'] or f['expired_instrument_key']
        
        if f['artifact_class'] == "RAW_CANDLE_RESPONSE":
            c['raw_candle_path'] = f['relative_path']
            c['raw_candle_sha256'] = f['sha256']
            if f['status'] == 'EMPTY':
                c['empty_response'] = True
        
        elif f['artifact_class'] == "NORMALIZED_1MIN":
            c['normalized_1m_path'] = f['relative_path']
            c['normalized_1m_sha256'] = f['sha256']
            c['one_minute_row_count'] = f['row_count'] or 0
            c['first_candle'] = f['first_timestamp']
            c['last_candle'] = f['last_timestamp']
            
            # calculate unique session count
            if f['status'] == 'VALID':
                pq_path = EVIDENCE_ROOT / f['relative_path']
                try:
                    df = pd.read_parquet(pq_path, columns=['timestamp'])
                    if not df.empty:
                        # assuming UTC isoformat strings
                        df['date'] = pd.to_datetime(df['timestamp']).dt.tz_convert('Asia/Kolkata').dt.date
                        c['unique_session_count'] = df['date'].nunique()
                except Exception:
                    pass
            
        elif f['artifact_class'] == "NORMALIZED_5MIN":
            c['normalized_5m_path'] = f['relative_path']
            c['normalized_5m_sha256'] = f['sha256']
            c['five_minute_row_count'] = f['row_count'] or 0
    
    # Read contract metadata from RAW_CONTRACT_INVENTORY
    for _, f in df_files[df_files['artifact_class'] == 'RAW_CONTRACT_INVENTORY'].iterrows():
        exp = f['expiry'] # Wait, contracts.json is per expiry
        if not exp:
            # try extract from path
            if "expiry=" in f['relative_path']:
                exp = f['relative_path'].split("expiry=")[1].split("/")[0]
        
        if exp:
            c_path = EVIDENCE_ROOT / f['relative_path']
            if c_path.exists():
                try:
                    with open(c_path, 'r') as cf:
                        cdat = json.load(cf)
                    if cdat.get('status') == 'success' and 'data' in cdat:
                        for d in cdat['data']:
                            opt = 'CE' if d.get('instrument_type') == 'CE' else 'PE' if d.get('instrument_type') == 'PE' else None
                            # Upstox doesn't put strike easily in API contracts response sometimes, wait, trading_symbol has it
                            # But we already have expired_instrument_key in 1m files. 
                            # Let's match by expired_instrument_key
                            inst_key = d.get('instrument_key')
                            for k, c in contracts.items():
                                if c['expiry'] == exp and c['expired_instrument_key'] == inst_key:
                                    c['exchange_token'] = d.get('exchange_token')
                                    c['lot_size'] = d.get('lot_size')
                                    c['minimum_lot'] = d.get('minimum_lot')
                                    c['weekly'] = d.get('weekly')
                                    c['raw_contract_metadata_path'] = f['relative_path']
                                    c['raw_contract_metadata_sha256'] = f['sha256']
                except Exception as e:
                    pass

    # Assign request_from_date and request_to_date based on deterministic rule
    for key, c in contracts.items():
        exp_date = datetime.strptime(c['expiry'], "%Y-%m-%d").date()
        from_date = get_thursday_before(exp_date)
        c['request_from_date'] = from_date.strftime("%Y-%m-%d")
        c['request_to_date'] = c['expiry']
        
        # Determine final_status
        if c['one_minute_row_count'] > 0 and c['five_minute_row_count'] > 0:
            c['final_status'] = "VALID_COMPLETE"
            c['status_reason'] = "Fully populated"
        elif c['one_minute_row_count'] > 0 and c['five_minute_row_count'] == 0:
            c['final_status'] = "VALID_1M_ONLY"
            c['status_reason'] = "Missing 5m aggregation"
        elif c['empty_response']:
            c['final_status'] = "AUTHORITATIVE_NO_DATA"
            c['status_reason'] = "Broker returned empty candles"
        elif not c['raw_candle_path']:
            c['final_status'] = "MISSING_RAW"
            c['status_reason'] = "No raw response found"
        elif not c['normalized_1m_path']:
            c['final_status'] = "MISSING_NORMALIZED"
            c['status_reason'] = "Raw found but not normalized"
            
    df_contracts = pd.DataFrame(list(contracts.values()))
    df_contracts.to_parquet(MANIFESTS_DIR / "contract_inventory.parquet", index=False)
    
    print(f"Generated contract_inventory.parquet with {len(df_contracts)} contracts.")

if __name__ == "__main__":
    main()
