#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_PATH="$HOME/.trading_bot/kite_access_token"

SKIP_LOGIN=0
FORCE_LOGIN=0
LOGIN_ONLY=0
VALIDATE_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --skip-login) SKIP_LOGIN=1 ;;
    --force-login) FORCE_LOGIN=1 ;;
    --login-only) LOGIN_ONLY=1 ;;
    --validate-only) VALIDATE_ONLY=1 ;;
    -h|--help)
      echo "Usage: ./run_live.sh [--skip-login] [--force-login] [--login-only] [--validate-only]"
      echo "  --skip-login   Do not run autologin; just validate token and start bot"
      echo "  --force-login  Always run autologin before starting bot"
      echo "  --login-only   Run autologin and final token validation, then exit"
      echo "  --validate-only Validate existing token and exit"
      exit 0
      ;;
    *)
      echo "[RUN_LIVE] Unknown arg: $arg"
      exit 2
      ;;
  esac
done

echo "[RUN_LIVE] Project: $ROOT_DIR"
echo "[RUN_LIVE] Token file: $TOKEN_PATH"

if [[ "$LOGIN_ONLY" -eq 1 && "$VALIDATE_ONLY" -eq 1 ]]; then
  echo "[RUN_LIVE] ERROR: --login-only and --validate-only cannot be used together."
  exit 2
fi

if [[ "$FORCE_LOGIN" -eq 1 && "$SKIP_LOGIN" -eq 1 ]]; then
  echo "[RUN_LIVE] ERROR: --force-login and --skip-login cannot be used together."
  exit 2
fi

if [[ -z "${KITE_API_KEY:-}" ]]; then
  echo "[RUN_LIVE] ERROR: KITE_API_KEY is not set in environment."
  echo "          Export it (or set in your shell profile) and re-run."
  exit 1
fi

TOKEN_VAL=""
if [[ -f "$TOKEN_PATH" ]]; then
  TOKEN_VAL="$(python - <<'PY'
from pathlib import Path
p = Path.home()/".trading_bot"/"kite_access_token"
print(p.read_text().strip() if p.exists() else "")
PY
)"
fi

token_len="${#TOKEN_VAL}"

validate_token() {
  python - <<'PY'
from core.auth_health import get_kite_auth_health

payload = get_kite_auth_health(force=True)
if not payload.get("ok"):
    print(f"[RUN_LIVE] Token invalid: {payload.get('error')}")
    raise SystemExit(12)
print(f"[RUN_LIVE] Token valid. user_id={payload.get('user_id')}")
PY
}

run_login() {
  if [[ -z "${KITE_API_SECRET:-}" ]]; then
    echo "[RUN_LIVE] ERROR: KITE_API_SECRET is not set in environment."
    echo "          Required for autologin."
    exit 1
  fi
  echo "[RUN_LIVE] Running Kite autologin..."
  python "$ROOT_DIR/scripts/kite_autologin_localhost.py"
}

if [[ "$FORCE_LOGIN" -eq 1 ]]; then
  run_login
elif [[ "$SKIP_LOGIN" -eq 1 ]]; then
  echo "[RUN_LIVE] --skip-login set; validating existing token only..."
else
  if [[ "$token_len" -ge 20 ]]; then
    echo "[RUN_LIVE] Found existing token; validating..."
    if ! validate_token; then
      echo "[RUN_LIVE] Existing token failed validation; re-authenticating..."
      run_login
    fi
  else
    echo "[RUN_LIVE] No usable token found; authenticating..."
    run_login
  fi
fi

echo "[RUN_LIVE] Final token validation..."
validate_token

if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
  echo "[RUN_LIVE] --validate-only complete. Exiting."
  exit 0
fi

if [[ "$LOGIN_ONLY" -eq 1 ]]; then
  echo "[RUN_LIVE] --login-only complete. Exiting."
  exit 0
fi

echo "[RUN_LIVE] Starting main.py ..."
python "$ROOT_DIR/main.py"
