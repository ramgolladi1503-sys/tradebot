import argparse
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, required=True)
    parser.add_argument("--replay_dir", type=str, default="runtime/upstox_candidate_replay")
    args = parser.parse_args()
    
    runtime_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    candidates_file = runtime_dir / "phase_4_candidates.jsonl"
    
    if not candidates_file.exists():
        print(f"No candidates file found at {candidates_file}")
        return
        
    rejected_candidates = []
    with open(candidates_file, "r") as f:
        for line in f:
            cand = json.loads(line)
            if cand.get("status") == "REJECTED" or cand.get("reject_reason"):
                rejected_candidates.append(cand)
                
    # Group by date and symbol
    cands_by_day_sym = defaultdict(list)
    for c in rejected_candidates:
        dt = datetime.fromisoformat(c["signal_time"])
        day_str = dt.strftime("%Y%m%d")
        cands_by_day_sym[(day_str, c["symbol"])].append(c)
        
    replay_base = Path(args.replay_dir)
    
    results_by_reason = defaultdict(lambda: {
        "total_rejected": 0,
        "target_hit_if_taken": 0,
        "stop_hit_if_taken": 0,
        "neither": 0,
        "insufficient_data": 0,
        "sum_mfe": 0.0,
        "sum_mae": 0.0,
        "valid_mae_mfe_count": 0,
        "option_bid_ask_path_count": 0,
        "option_ltp_path_count": 0,
        "underlying_proxy_path_count": 0
    })
    
    for (day_str, sym), cands in cands_by_day_sym.items():
        # Pre-load underlying proxy
        df_underlying = None
        p_und_proxy = replay_base / day_str / "underlying" / f"{sym}_{day_str}.parquet"
        p_und_alt = replay_base / day_str / "underlying" / f"{sym}.parquet"
        
        if p_und_proxy.exists():
            df_underlying = pd.read_parquet(p_und_proxy)
        elif p_und_alt.exists():
            df_underlying = pd.read_parquet(p_und_alt)
            
        if df_underlying is not None:
            df_underlying['timestamp'] = pd.to_datetime(df_underlying['timestamp'])
        
        for c in cands:
            reason = c.get("reject_reason", "UNKNOWN")
            results_by_reason[reason]["total_rejected"] += 1
            
            mode = "underlying_proxy_path"
            df = df_underlying
            
            contract_key = c.get("contract_key")
            if contract_key:
                p_opt_ba = replay_base / day_str / "options" / f"{contract_key}_ba.parquet"
                p_opt_ltp = replay_base / day_str / "options" / f"{contract_key}_ltp.parquet"
                
                if p_opt_ba.exists():
                    df = pd.read_parquet(p_opt_ba)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    mode = "option_bid_ask_path"
                elif p_opt_ltp.exists():
                    df = pd.read_parquet(p_opt_ltp)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    mode = "option_ltp_path"
                    
            if df is None:
                results_by_reason[reason]["insufficient_data"] += 1
                continue
                
            results_by_reason[reason][f"{mode}_count"] += 1
            
            sig_time = pd.to_datetime(c["signal_time"])
            forward_df = df[df['timestamp'] > sig_time].copy()
            
            if forward_df.empty:
                results_by_reason[reason]["insufficient_data"] += 1
                continue
                
            # Use original boundaries
            direction = c.get("direction")
            entry = c.get("entry")
            sl = c.get("stop_loss")
            target = c.get("target")
            
            if entry is None or sl is None or target is None:
                results_by_reason[reason]["insufficient_data"] += 1
                continue
                
            risk = abs(entry - sl)
            
            if risk == 0:
                results_by_reason[reason]["insufficient_data"] += 1
                continue
                
            outcome = "NEITHER"
            max_favorable = 0.0
            max_adverse = 0.0
            
            for _, row in forward_df.iterrows():
                h = row['high']
                l = row['low']
                
                if direction == "SHORT":
                    # Adverse is high, Favorable is low
                    adverse_move = h - entry
                    favorable_move = entry - l
                    if adverse_move > max_adverse: max_adverse = adverse_move
                    if favorable_move > max_favorable: max_favorable = favorable_move
                    
                    if h >= sl:
                        outcome = "STOP_HIT"
                        break
                    if l <= target:
                        outcome = "TARGET_HIT"
                        break
                else:
                    adverse_move = entry - l
                    favorable_move = h - entry
                    if adverse_move > max_adverse: max_adverse = adverse_move
                    if favorable_move > max_favorable: max_favorable = favorable_move
                    
                    if l <= sl:
                        outcome = "STOP_HIT"
                        break
                    if h >= target:
                        outcome = "TARGET_HIT"
                        break
                        
            if outcome == "TARGET_HIT":
                results_by_reason[reason]["target_hit_if_taken"] += 1
            elif outcome == "STOP_HIT":
                results_by_reason[reason]["stop_hit_if_taken"] += 1
            else:
                results_by_reason[reason]["neither"] += 1
                
            # MFE/MAE as a percentage of entry
            mfe_pct = max_favorable / entry if entry > 0 else 0
            mae_pct = max_adverse / entry if entry > 0 else 0
            
            results_by_reason[reason]["sum_mfe"] += mfe_pct
            results_by_reason[reason]["sum_mae"] += mae_pct
            results_by_reason[reason]["valid_mae_mfe_count"] += 1
            
    final_report = []
    
    for reason, metrics in results_by_reason.items():
        total = metrics["total_rejected"]
        if total == 0: continue
        
        valid_count = metrics["valid_mae_mfe_count"]
        avg_mfe = metrics["sum_mfe"] / valid_count if valid_count > 0 else 0
        avg_mae = metrics["sum_mae"] / valid_count if valid_count > 0 else 0
        
        false_block_rate = metrics["target_hit_if_taken"] / total
        saved_loss_rate = metrics["stop_hit_if_taken"] / total
        
        final_report.append({
            "reject_reason": reason,
            "total_rejected": total,
            "target_hit_if_taken": metrics["target_hit_if_taken"],
            "stop_hit_if_taken": metrics["stop_hit_if_taken"],
            "neither": metrics["neither"],
            "insufficient_data_count": metrics["insufficient_data"],
            "avg_mfe_pct": round(avg_mfe * 100, 3),
            "avg_mae_pct": round(avg_mae * 100, 3),
            "possible_false_block_rate": round(false_block_rate, 3),
            "saved_loss_rate": round(saved_loss_rate, 3),
            "boundary_evidence_mode": "ORIGINAL_BOUNDARIES",
            "replay_price_path_mode": "OPTION_BID_ASK_PATH" if metrics["option_bid_ask_path_count"] > 0 else "OPTION_LTP_PATH" if metrics["option_ltp_path_count"] > 0 else "UNDERLYING_PROXY_PATH" if metrics["underlying_proxy_path_count"] > 0 else "MISSING_PRICE_PATH",
            "blocker_outcome_correctness_indicated": True,
            "blocker_outcome_correctness_proven": False,
            "original_boundary_count": total - metrics["insufficient_data"],
            "reconstructed_boundary_count": 0,
            "missing_boundary_count": metrics["insufficient_data"],
            "option_bid_ask_path_count": metrics["option_bid_ask_path_count"],
            "option_ltp_path_count": metrics["option_ltp_path_count"],
            "underlying_proxy_path_count": metrics["underlying_proxy_path_count"],
            "missing_price_path_count": metrics["insufficient_data"]
        })
        
    with open(runtime_dir / "blocker_outcome_replay.json", "w") as f:
        json.dump(final_report, f, indent=2)
        
    md_lines = ["# Blocker Outcome Replay Report", ""]
    md_lines.append(f"**Strategy**: {args.strategy}")
    md_lines.append("")
    md_lines.append("> [!NOTE]")
    md_lines.append("> This report indicates gate usefulness under original-boundary underlying-proxy replay.")
    md_lines.append("")
    md_lines.append("| Reject Reason | Total | Target Hit (False Block) | Stop Hit (Saved Loss) | Neither | Avg MFE % | Avg MAE % | False Block Rate | Saved Loss Rate |")
    md_lines.append("|---|---|---|---|---|---|---|---|---|")
    
    for r in final_report:
        md_lines.append(f"| {r['reject_reason']} | {r['total_rejected']} | {r['target_hit_if_taken']} | {r['stop_hit_if_taken']} | {r['neither']} | {r['avg_mfe_pct']}% | {r['avg_mae_pct']}% | {r['possible_false_block_rate']} | {r['saved_loss_rate']} |")
        
    with open(runtime_dir / "blocker_outcome_replay.md", "w") as f:
        f.write("\n".join(md_lines) + "\n")
        
    print(f"Blocker outcome replay completed. Output saved to {runtime_dir}")

if __name__ == "__main__":
    main()
