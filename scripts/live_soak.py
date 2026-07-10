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
    
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    metrics = []
    
    try:
        while datetime.datetime.now() < end_time:
            time.sleep(60)
            
            # Read health
            logs_root = Path(".runtime") / "logs"
            health_path = logs_root / "runtime_health_latest.json"
            pipe_path = logs_root / "ranked_pipeline_runtime_latest.json"
            feed_path = logs_root / "feed_truth_latest.json"
            depth_ws_path = logs_root / "depth_ws_watchdog.log"
            
            m = {"ts": datetime.datetime.now().isoformat()}
            try:
                if health_path.exists():
                    with health_path.open() as f:
                        h = json.load(f)
                        m["feed_ok"] = h.get("feed_ok")
                        m["ws_connected"] = h.get("feed_status", {}).get("ws_connected")
            except: pass
            
            try:
                if pipe_path.exists():
                    with pipe_path.open() as f:
                        p = json.load(f)
                        m["candidates"] = p.get("candidates_considered", 0)
                        m["advisory"] = p.get("top_advisory_opportunities", 0)
                        m["executable"] = p.get("top_executable_opportunities", 0)
            except: pass
            
            metrics.append(m)
            print(f"Collected metrics at {m['ts']}: {m}")
            
    except KeyboardInterrupt:
        print("Interrupted by user")
    
    # generate report
    with open(report_path, "w") as f:
        f.write("# Live Soak Report\n")
        f.write(f"Start: {now}\n")
        f.write(f"End: {datetime.datetime.now()}\n")
        f.write(f"Metrics: {json.dumps(metrics, indent=2)}\n")
        
    print(f"Report written to {report_path}")
    bot_proc.terminate()

if __name__ == "__main__":
    run()
