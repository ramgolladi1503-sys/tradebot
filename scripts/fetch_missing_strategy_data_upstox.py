import os
import requests

def fetch_data(manifest, out_dir, mode="real_upstox"):
    if mode == "fixture":
        return {
            "certification_eligible": False,
            "data_source": "synthetic_test_fixture",
            "lifecycle_state": "DATA_FETCH_SIMULATED_NOT_CERTIFIABLE"
        }
        
    if mode == "real_upstox":
        if "UPSTOX_ACCESS_TOKEN" not in os.environ:
            return {"auth_error": True, "certification_eligible": False}
            
        res = requests.get("https://api.upstox.com/v2/historical-candle")
        if res.status_code == 401:
            return {"auth_error": True, "certification_eligible": False}
            
        data = res.json().get("data", {}).get("candles", [])
        if not data:
            return {"data_unavailable_count": 1, "certification_eligible": False}
            
        return {"succeeded": 1, "certification_eligible": True}
        
    return {}
