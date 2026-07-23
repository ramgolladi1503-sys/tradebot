import json
import gzip
from pathlib import Path
from datetime import datetime

def main():
    raw_dir = Path("runtime/constituent_lead_lag/upstox_v1/raw")
    reports_dir = Path("runtime/constituent_lead_lag/upstox_v1/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    if not raw_dir.exists():
        print("Raw directory not found.")
        return
        
    validation_results = []
    
    for gz_file in raw_dir.glob("*.json.gz"):
        filename = gz_file.name
        sym = filename.split("_")[0]
        
        try:
            with gzip.open(gz_file, "rt") as f:
                data = json.load(f)
                
            candles = data.get("data", {}).get("candles", [])
            
            passed = True
            reason = ""
            
            if not candles:
                passed = False
                reason = "Length is 0"
            else:
                last_ts = None
                all_zeros = True
                for c in candles:
                    # c[0] is ts, c[1] is open, c[2] high, c[3] low, c[4] close
                    ts = datetime.fromisoformat(c[0].replace('+05:30', ''))
                    if last_ts and ts <= last_ts:
                        # Upstox returns newest first in some APIs, let's just check if it's strictly ordered (ascending or descending)
                        # The validation asks for "strictly monotonically increasing" which means we should sort first or check it.
                        # Actually Upstox v2 returns newest first. So we should sort them by timestamp.
                        pass # Let's handle sorting/ordering properly.
                        
                    if float(c[1]) != 0 or float(c[4]) != 0:
                        all_zeros = False
                
                # Verify strictly monotonically increasing after sorting
                candles_sorted = sorted(candles, key=lambda x: datetime.fromisoformat(x[0].replace('+05:30', '')))
                
                last_ts = None
                for c in candles_sorted:
                    ts = datetime.fromisoformat(c[0].replace('+05:30', ''))
                    if last_ts and ts <= last_ts:
                        passed = False
                        reason = "Timestamps not strictly monotonically increasing"
                        break
                    last_ts = ts
                    
                if all_zeros:
                    passed = False
                    reason = "Values are entirely zero"
                    
            validation_results.append({
                "file": filename,
                "symbol": sym,
                "passed": passed,
                "reason": reason,
                "candles_count": len(candles)
            })
            
        except Exception as e:
            validation_results.append({
                "file": filename,
                "symbol": sym,
                "passed": False,
                "reason": str(e),
                "candles_count": 0
            })
            
    with open(reports_dir / "data_quality.json", "w") as f:
        json.dump(validation_results, f, indent=2)
        
    passed_count = sum(1 for r in validation_results if r["passed"])
    print(f"Validated {len(validation_results)} files. Passed: {passed_count}, Failed: {len(validation_results) - passed_count}")

if __name__ == "__main__":
    main()
