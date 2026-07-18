import json
from pathlib import Path
from research.opening_state_momentum.development_wfa_contract import build_contract

def main():
    contract = build_contract()
    out_dir = Path("docs/agent_reviews/opening_state_momentum")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "development_wfa_contract.json"
    
    with open(out_path, "w") as f:
        json.dump(contract, f, indent=2)
    print(f"Generated {out_path}")

if __name__ == "__main__":
    main()
