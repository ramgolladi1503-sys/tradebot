import argparse
import sys
import json
import importlib.util
import inspect
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.movement_contract import StrategyContext, StrategyCandidate, candidate_from_dict
from core.movement_regime import MovementRegimeResult
import time

def run_audit(strategy_id: str, module_path: str, callable_name: str) -> dict:
    result = {
        "strategy_id": strategy_id,
        "callable_exists": False,
        "returns_list_or_tuple": False,
        "contract_passed": False,
        "errors": []
    }
    
    try:
        spec = importlib.util.spec_from_file_location(f"audit_module_{strategy_id}", module_path)
        if not spec or not spec.loader:
            result["errors"].append("Module spec not found")
            return result
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        result["errors"].append(f"Failed to load module: {e}")
        return result
        
    func = getattr(mod, callable_name, None)
    if not func:
        result["errors"].append(f"Callable {callable_name} not found in {module_path}")
        return result
        
    result["callable_exists"] = True
    
    ctx = StrategyContext(
        symbol="NIFTY",
        ts_epoch=time.time(),
        spot_ltp=100.0,
        vwap=100.0,
        vwap_slope=0.0,
        range_width_pct=0.01,
        volume_z=1.0,
        ce_spread_pct=0.01,
        pe_spread_pct=0.01
    )
    regime = MovementRegimeResult(
        schema_version=1,
        primary_regime="CHOP",
        scores={"CHOP": 1.0}
    )
    
    sig = inspect.signature(func)
    kwargs = {}
    if "ctx" in sig.parameters:
        kwargs["ctx"] = ctx
    if "regime" in sig.parameters:
        kwargs["regime"] = regime
        
    try:
        candidates = func(**kwargs)
        if isinstance(candidates, (list, tuple)):
            result["returns_list_or_tuple"] = True
        else:
            result["errors"].append("Does not return a list or tuple of candidates")
            return result
            
        for cand in candidates:
            if isinstance(cand, dict):
                cand = candidate_from_dict(cand)
            if not isinstance(cand, StrategyCandidate):
                result["errors"].append("Item is not a StrategyCandidate")
                continue
                
            if not getattr(cand, "strategy_id", None):
                result["errors"].append("Missing strategy_id")
            if not getattr(cand, "generated_epoch", None):
                result["errors"].append("Missing generated_epoch")
            if not getattr(cand, "direction", None):
                result["errors"].append("Missing direction")
                
            if cand.status in ("NO_TRADE", "ADVISORY", "FALLBACK") and cand.executable_eligible:
                result["errors"].append("fallback/advisory candidates cannot be executable")
                
        if not result["errors"]:
            result["contract_passed"] = True
            
    except Exception as e:
        import traceback
        result["errors"].append(f"Execution failed: {traceback.format_exc()}")
        
    if len(result["errors"]) == 0 and result["returns_list_or_tuple"]:
        result["contract_passed"] = True

    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--module-path", required=True)
    parser.add_argument("--callable-name", required=True)
    parser.add_argument("--output-report", required=True)
    args = parser.parse_args()
    
    rep = run_audit(args.strategy_id, args.module_path, args.callable_name)
    
    if rep["contract_passed"]:
        rep["state"] = "CANDIDATE_GENERATOR_CONTRACT_PASSED"
    elif rep["callable_exists"]:
        rep["state"] = "CANDIDATE_GENERATOR_CONTRACT_FAILED"
    else:
        rep["state"] = "NOT_A_STRATEGY_MODULE"
        
    out = Path(args.output_report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=4))
    
    print(f"Audit written to {args.output_report}")
    
if __name__ == "__main__":
    main()
