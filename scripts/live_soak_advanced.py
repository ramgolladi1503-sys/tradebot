import os
import sys
import time
import json
import datetime
import subprocess
from pathlib import Path

def run():
    now = datetime.datetime.now()
    folder_name = now.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("runtime", "live_observation", folder_name)
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "live_soak_report.md")
    
    print(f"Starting live soak at {now}")
    print(f"Output directory: {out_dir}")
    
    bot_proc = subprocess.Popen(["bash", "scripts/run_all.sh"])
    
    # Run for 2 hours (120 minutes) or until 15:30
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    metrics = []
    
    try:
        while datetime.datetime.now() < end_time:
            time.sleep(60)
            
            m = {"ts": datetime.datetime.now().isoformat()}
            
            # Read health
            logs_root = Path(".runtime") / "logs"
            health_path = logs_root / "runtime_health_latest.json"
            if health_path.exists():
                try:
                    with health_path.open() as f:
                        h = json.load(f)
                        m["feed_ok"] = h.get("feed_ok")
                        m["ws_connected"] = h.get("feed_status", {}).get("ws_connected")
                        m["last_any_packet_age"] = h.get("feed_status", {}).get("latest_packet_age_sec")
                except: pass
                
            feed_path = logs_root / "feed_truth_latest.json"
            if feed_path.exists():
                try:
                    with feed_path.open() as f:
                        feed = json.load(f)
                        m["NO_LIVE_OPTION_FEED"] = feed.get("NO_LIVE_OPTION_FEED", False)
                        m["tick_stalled"] = feed.get("tick_stalled", False)
                except: pass

            pipe_path = logs_root / "ranked_pipeline_runtime_latest.json"
            if pipe_path.exists():
                try:
                    with pipe_path.open() as f:
                        p = json.load(f)
                        m["candidates"] = p.get("candidates_considered", 0)
                        m["advisory"] = p.get("top_advisory_opportunities", 0)
                        m["executable"] = p.get("top_executable_opportunities", 0)
                except: pass
            
            metrics.append(m)
            print(f"Collected metrics at {m['ts']}: feed_ok={m.get('feed_ok')} executable={m.get('executable')}")
            
    except KeyboardInterrupt:
        print("Interrupted by user")
    
    # Generate report
    with open(report_path, "w") as f:
        f.write("# Live Soak Report\n\n")
        f.write(f"**Start**: {now}\n")
        f.write(f"**End**: {datetime.datetime.now()}\n")
        
        feed_ok_count = sum(1 for x in metrics if x.get("feed_ok"))
        total = len(metrics)
        pct = (feed_ok_count / total * 100) if total > 0 else 0
        
        f.write(f"**Feed OK Uptime**: {pct:.2f}%\n")
        f.write(f"**Total Mins**: {total}\n\n")
        
        executables = sum(x.get("executable", 0) for x in metrics)
        f.write(f"**Any Candidate Became Executable**: {'Yes' if executables > 0 else 'No'}\n\n")
        
        f.write("## Recommendation\n")
        if pct > 90:
            f.write("Status: **Stable**\n")
        else:
            f.write("Status: **Unstable**\n")
            
    print(f"Report written to {report_path}")
    bot_proc.terminate()

if __name__ == "__main__":
    run()
