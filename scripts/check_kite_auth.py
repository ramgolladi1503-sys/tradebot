from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


from core.auth_health import get_kite_auth_health

if __name__ == "__main__":
    payload = get_kite_auth_health(force=True)
    print("Auth OK:", payload.get("ok"))
    print("Error:", payload.get("error"))
    user_id = payload.get("user_id") or ""
    user_name = payload.get("user_name") or ""
    if user_id or user_name:
        print("User:", f"{user_id} {user_name}".strip())
