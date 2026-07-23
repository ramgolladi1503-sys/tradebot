import json
import os
import hashlib
from pathlib import Path

def get_sha256(path):
    hash_sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except:
        return None

def main():
    search_dirs = [
        "/Users/madhuram/tradebot/runtime",
        "/Users/madhuram/tradebot-ml-evidence",
        "/Users/madhuram/tradebot-constituent-lead-lag-v1/runtime"
    ]
    extensions = [".parquet", ".csv", ".json", ".json.gz", ".zip"]
    
    keywords = ["nifty", "banknifty", "constituent", "weight", "upstox", "instrument", "5m"]
    
    inventory = []
    
    for search_dir in search_dirs:
        for root, dirs, files in os.walk(search_dir):
            for file in files:
                if any(file.endswith(ext) for ext in extensions):
                    if any(kw in file.lower() for kw in keywords):
                        full_path = Path(root) / file
                        try:
                            stat = full_path.stat()
                            
                            # Determine classification based on filename
                            provider = "upstox" if "upstox" in file.lower() else "unknown"
                            usable = False
                            rejection_reason = "Not parsed/verified yet"
                            
                            inventory.append({
                                "path": str(full_path),
                                "size": stat.st_size,
                                "sha256": get_sha256(full_path) if stat.st_size < 100 * 1024 * 1024 else "skipped_too_large",
                                "format": full_path.suffix,
                                "provider": provider,
                                "synthetic": False,
                                "mock": False,
                                "fallback": False,
                                "usable": usable,
                                "rejection_reason": rejection_reason
                            })
                        except Exception as e:
                            pass

    out_dir = Path("/Users/madhuram/tradebot-constituent-lead-lag-v1/runtime/constituent_lead_lag/upstox_v1/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "local_data_inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)
        
    with open(out_dir / "local_data_inventory.md", "w") as f:
        f.write("# Local Data Inventory\n\n")
        f.write("| Path | Size | Provider | Usable | Reason |\n")
        f.write("|---|---|---|---|---|\n")
        for item in inventory:
            f.write(f"| {Path(item['path']).name} | {item['size']} | {item['provider']} | {item['usable']} | {item['rejection_reason']} |\n")

if __name__ == "__main__":
    main()
