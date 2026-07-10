import json
from pathlib import Path

def generate_report():
    sources = [
        "UPSTOX_UNDERLYING_OHLC",
        "UPSTOX_OPTION_OHLC",
        "LIVE_CAPTURED_OPTION_QUOTES",
        "LIVE_CAPTURED_OPTION_DEPTH",
        "BROKER_HISTORICAL_OPTION_TICKS",
        "FIXTURE_DATA",
        "MOCK_DATA",
        "SYNTHETIC_DATA",
        "PROXY_DATA"
    ]
    
    report_data = []
    
    for source in sources:
        item = {
            "source": source,
            "usable_for_setup_reconstruction": False,
            "usable_for_option_candle_replay": False,
            "usable_for_stress_replay": False,
            "certifiable_for_candidate_replay": False,
            "has_underlying_ohlc": False,
            "has_option_ohlc": False,
            "has_option_ltp_truth": False,
            "has_bid_ask_spread_truth": False,
            "has_depth_truth": False,
            "allowed_modes": [],
            "blocked_modes": ["stress"],
            "blockers": ["DATA_BLOCKED_STRESS_REPLAY_UNSUPPORTED_BY_DATA_CAPABILITY"],
            "notes": ""
        }
        
        if source == "UPSTOX_UNDERLYING_OHLC":
            item["usable_for_setup_reconstruction"] = True
            item["has_underlying_ohlc"] = True
            item["blockers"] = ["DATA_BLOCKED_UNDERLYING_ONLY_NO_OPTION_TRUTH"]
            item["notes"] = "Upstox underlying OHLC can support setup reconstruction only."
            
        elif source == "UPSTOX_OPTION_OHLC":
            item["usable_for_setup_reconstruction"] = True
            item["usable_for_option_candle_replay"] = True
            item["has_underlying_ohlc"] = True
            item["has_option_ohlc"] = True
            item["has_option_ltp_truth"] = True
            item["blockers"] = ["DATA_BLOCKED_OPTION_OHLC_NO_SPREAD_TRUTH"]
            item["notes"] = "Upstox option OHLC can support candle replay only if the harness has an explicit candle replay mode. Upstox OHLC cannot support stress replay without bid/ask spread or depth truth."
            
        elif source == "LIVE_CAPTURED_OPTION_QUOTES":
            item["usable_for_setup_reconstruction"] = True
            item["usable_for_option_candle_replay"] = True
            item["usable_for_stress_replay"] = True
            item["certifiable_for_candidate_replay"] = True
            item["has_underlying_ohlc"] = True
            item["has_option_ohlc"] = True
            item["has_option_ltp_truth"] = True
            item["has_bid_ask_spread_truth"] = True
            item["allowed_modes"] = ["stress", "candle"]
            item["blocked_modes"] = []
            item["blockers"] = []
            item["notes"] = "Live captured option quotes may support option LTP and spread-aware checks if quote contains bid/ask."
            
        elif source == "LIVE_CAPTURED_OPTION_DEPTH":
            item["usable_for_setup_reconstruction"] = True
            item["usable_for_option_candle_replay"] = True
            item["usable_for_stress_replay"] = True
            item["certifiable_for_candidate_replay"] = True
            item["has_underlying_ohlc"] = True
            item["has_option_ohlc"] = True
            item["has_option_ltp_truth"] = True
            item["has_bid_ask_spread_truth"] = True
            item["has_depth_truth"] = True
            item["allowed_modes"] = ["stress", "candle"]
            item["blocked_modes"] = []
            item["blockers"] = []
            item["notes"] = "Live captured depth may support stress replay if coverage/provenance is complete."
            
        elif source == "BROKER_HISTORICAL_OPTION_TICKS":
            item["usable_for_setup_reconstruction"] = True
            item["usable_for_option_candle_replay"] = True
            item["usable_for_stress_replay"] = True
            item["certifiable_for_candidate_replay"] = True
            item["has_underlying_ohlc"] = True
            item["has_option_ohlc"] = True
            item["has_option_ltp_truth"] = True
            item["has_bid_ask_spread_truth"] = True
            item["has_depth_truth"] = False
            item["allowed_modes"] = ["stress", "candle"]
            item["blocked_modes"] = []
            item["blockers"] = []
            item["notes"] = "Historical ticks with spread data can support stress replay."
            
        elif source in ["FIXTURE_DATA", "MOCK_DATA", "SYNTHETIC_DATA", "PROXY_DATA"]:
            item["notes"] = f"{source} must be non-certifiable."
            
        report_data.append(item)
        
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = out_dir / "candidate_replay_data_source_decision_report.json"
    with open(json_path, "w") as f:
        json.dump(report_data, f, indent=2)
        
    md_path = out_dir / "candidate_replay_data_source_decision_report.md"
    with open(md_path, "w") as f:
        f.write("# Candidate Replay Data Source Decision Report\n\n")
        f.write("| Source | Setup | Candle | Stress | Certifiable | Blockers |\n")
        f.write("|--------|-------|--------|--------|-------------|----------|\n")
        for item in report_data:
            setup = "✅" if item["usable_for_setup_reconstruction"] else "❌"
            candle = "✅" if item["usable_for_option_candle_replay"] else "❌"
            stress = "✅" if item["usable_for_stress_replay"] else "❌"
            cert = "✅" if item["certifiable_for_candidate_replay"] else "❌"
            blockers = ", ".join(item["blockers"])
            f.write(f"| {item['source']} | {setup} | {candle} | {stress} | {cert} | {blockers} |\n")
            
        f.write("\n## Notes\n")
        for item in report_data:
            f.write(f"- **{item['source']}**: {item['notes']}\n")

if __name__ == "__main__":
    generate_report()
