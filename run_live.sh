#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TOKEN_PATH="${TRADEBOT_ACCESS_TOKEN_PATH:-$HOME/.tradebot/credentials/kite_access_token}"
READ_ONLY_OBSERVATION=0

echo "[RUN_LIVE] ROOT_DIR=$ROOT_DIR"
echo "[RUN_LIVE] TOKEN_PATH=$TOKEN_PATH"

export DATA_ROOT="${DATA_ROOT:-${TRADEBOT_EXTERNAL_RUNTIME_ROOT:-/Volumes/TradeBotData/tradebot-os/live/current-main}}"
export DESKS_ROOT="${DESKS_ROOT:-$DATA_ROOT/desks}"
export LOGS_ROOT="${LOGS_ROOT:-$DATA_ROOT/logs}"
export REPORTS_ROOT="${REPORTS_ROOT:-$DATA_ROOT/reports}"
export LOCKS_ROOT="${LOCKS_ROOT:-$DATA_ROOT/locks}"
export DB_ROOT="${DB_ROOT:-$DATA_ROOT/db}"

ensure_runtime_dirs() {
  local d=""
  for d in "$DATA_ROOT" "$DESKS_ROOT" "$LOGS_ROOT" "$REPORTS_ROOT" "$LOCKS_ROOT" "$DB_ROOT" "$ROOT_DIR/.runtime"; do
    if ! mkdir -p "$d" 2>/dev/null; then
      echo "[RUN_LIVE][ERROR] runtime_dir_not_writable path=$d"
      exit 2
    fi
  done
}

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
    --read-only-observation) READ_ONLY_OBSERVATION=1 ;;
    --preflight-only) VALIDATE_ONLY=1 ;;
    -h|--help)
      echo "Usage: ./run_live.sh [--skip-login] [--force-login] [--login-only] [--validate-only|--preflight-only|--read-only-observation]"
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
ensure_runtime_dirs

repair_stale_runtime_locks() {
  python - <<'PY'
from core.startup_recovery import reap_stale_runtime_locks

payload = reap_stale_runtime_locks()
print(f"[RUN_LIVE] stale_lock_recovery reaped={int(payload.get('reaped_count') or 0)}")
for item in list(payload.get("stale_locks") or []):
    print(
        "[RUN_LIVE] stale_lock_reaped "
        f"name={item.get('lock_name')} "
        f"pid={item.get('pid')} "
        f"action={item.get('action')}"
    )
PY
}

publish_auth_blocked_startup_state() {
  local startup_reason="$1"
  python - "$startup_reason" <<'PY'
import sys
from core.startup_recovery import publish_auth_blocked_startup_state

payload = publish_auth_blocked_startup_state(
    reason=str(sys.argv[1]),
    source="run_live.validate_token",
)
print(
    "[RUN_LIVE] startup_auth_blocked "
    f"auth_state={payload.get('auth_state')} "
    f"runtime_state={payload.get('runtime_state')}"
)
PY
}

if [[ "${STARTUP_STALE_LOCK_RECOVERY_ENABLE:-true}" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee]?[Ss])$ ]]; then
  repair_stale_runtime_locks
fi

configure_openmp_runtime() {
  local py_arch=""
  local conda_lib=""
  local selected_dir=""
  local candidate=""
  local info=""
  local checked_any=0

  py_arch="$(python -c "import platform; print(platform.machine())" 2>/dev/null || uname -m)"
  if [[ -n "${CONDA_PREFIX:-}" ]]; then
    conda_lib="${CONDA_PREFIX}/lib"
    candidate="${conda_lib}/libomp.dylib"
    if [[ -f "$candidate" ]]; then
      checked_any=1
      info="$(file "$candidate" 2>/dev/null || true)"
      if [[ "$py_arch" == "arm64" && "$info" == *"arm64"* ]]; then
        selected_dir="$conda_lib"
      elif [[ "$py_arch" != "arm64" && "$info" == *"x86_64"* ]]; then
        selected_dir="$conda_lib"
      fi
    fi
  fi

  if [[ -z "$selected_dir" ]]; then
    for candidate in "/opt/homebrew/opt/libomp/lib/libomp.dylib" "/usr/local/opt/libomp/lib/libomp.dylib"; do
      if [[ ! -f "$candidate" ]]; then
        continue
      fi
      checked_any=1
      info="$(file "$candidate" 2>/dev/null || true)"
      if [[ "$py_arch" == "arm64" && "$info" == *"arm64"* ]]; then
        selected_dir="$(dirname "$candidate")"
        break
      fi
      if [[ "$py_arch" != "arm64" && "$info" == *"x86_64"* ]]; then
        selected_dir="$(dirname "$candidate")"
        break
      fi
    done
  fi

  if [[ -n "$selected_dir" ]]; then
    export DYLD_LIBRARY_PATH="$selected_dir:${DYLD_LIBRARY_PATH:-}"
    export DYLD_FALLBACK_LIBRARY_PATH="$selected_dir:${DYLD_FALLBACK_LIBRARY_PATH:-}"
    echo "[RUN_LIVE] OpenMP runtime path configured: $selected_dir (py_arch=$py_arch)"
    return 0
  fi

  if [[ "$checked_any" -eq 1 ]]; then
    echo "[RUN_LIVE][WARN] libomp found but architecture mismatched for py_arch=$py_arch; xgboost may run in degraded mode."
  else
    echo "[RUN_LIVE][WARN] libomp.dylib not found; xgboost may run in degraded mode."
  fi
  if [[ -n "${CONDA_PREFIX:-}" ]]; then
    echo "[RUN_LIVE][HINT] Install ARM-compatible runtime in conda:"
    echo "  conda install -n ${CONDA_DEFAULT_ENV:-tradebot} -c conda-forge llvm-openmp py-xgboost"
  fi
  return 0
}

is_truthy() {
  [[ "${1:-}" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee]?[Ss])$ ]]
}

resolve_live_predictor_startup_mode() {
  local operator_override="${LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD:-}"
  if [[ -n "$operator_override" ]]; then
    if is_truthy "$operator_override"; then
      export LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD="true"
    else
      export LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD="false"
    fi
    echo "[RUN_LIVE] honoring operator predictor override LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD=$LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD"
    return 0
  fi

  echo "[RUN_LIVE] Probing persisted predictor startup health..."
  if env EXECUTION_MODE=LIVE TRADING_MODE=LIVE LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD=false python - <<'PY' >/dev/null 2>&1
from ml.trade_predictor import TradePredictor

TradePredictor(load_existing=True)
PY
  then
    export LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD="false"
    echo "[RUN_LIVE] persisted predictor startup probe passed; keeping live model load enabled."
  else
    export LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD="true"
    echo "[RUN_LIVE][WARN] persisted predictor startup probe failed; enabling startup-safe predictor fallback."
  fi
}

if [[ "$LOGIN_ONLY" -eq 1 && "$VALIDATE_ONLY" -eq 1 ]]; then
  echo "[RUN_LIVE] ERROR: --login-only and --validate-only cannot be used together."
  exit 2
fi

if [[ "$FORCE_LOGIN" -eq 1 && "$SKIP_LOGIN" -eq 1 ]]; then
  echo "[RUN_LIVE] ERROR: --force-login and --skip-login cannot be used together."
  exit 2
fi

if [[ -z "${KITE_API_KEY:-}" ]]; then
  if [[ -r "${TRADEBOT_KITE_CREDENTIAL_FILE:-$HOME/.tradebot/credentials/kite_app.env}" ]]; then
    # The helper validates and exports only the two allow-listed variables;
    # it never prints values or evaluates arbitrary shell content.
    source "$ROOT_DIR/scripts/live_credentials.sh"
  fi
fi

if [[ -z "${KITE_API_KEY:-}" ]]; then
  echo "[RUN_LIVE] ERROR: governed KITE_API_KEY binding is missing."
  echo "          Configure the private credential file or an approved environment binding."
  exit 1
fi

preflight_api_key() {
  # Fail fast if the api_key itself is invalid/expired. Otherwise the autologin
  # flow can hang behind a browser tab that never reaches a usable request_token.
  python - <<'PY'
import os
import sys
import urllib.request
import urllib.error

api_key = str(os.getenv("KITE_API_KEY", "") or "").strip()
if not api_key:
    sys.exit(0)

# Do not print api_key or URL. Only emit a safe tail marker.
tail4 = api_key[-4:] if len(api_key) >= 4 else api_key
url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"

try:
    with urllib.request.urlopen(url, timeout=8) as resp:
        body = resp.read(512) or b""
except urllib.error.HTTPError as exc:
    # Some environments return JSON even on 4xx.
    try:
        body = exc.read(512) or b""
    except Exception:
        body = b""
except Exception as exc:
    # Network/bot-protection hiccups should not be treated as invalid credentials.
    print(f"[RUN_LIVE][WARN] api_key_preflight_unavailable api_key_tail4={tail4} err={type(exc).__name__}")
    sys.exit(0)

text = body.decode("utf-8", "ignore").lower()
if "invalid" in text and "api_key" in text:
    print(f"[RUN_LIVE] ERROR: Zerodha rejected KITE_API_KEY (invalid api_key). api_key_tail4={tail4}")
    print("[RUN_LIVE]        Update KITE_API_KEY/KITE_API_SECRET to the current app values, then re-run.")
    sys.exit(13)
sys.exit(0)
PY
}

preflight_api_key || exit $?

RUN_LIVE_CONFIGURE_OPENMP_RUNTIME="${RUN_LIVE_CONFIGURE_OPENMP_RUNTIME:-false}"
if [[ "$RUN_LIVE_CONFIGURE_OPENMP_RUNTIME" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee]?[Ss])$ ]]; then
  configure_openmp_runtime
else
  echo "[RUN_LIVE] Skipping OpenMP runtime injection (set RUN_LIVE_CONFIGURE_OPENMP_RUNTIME=true to re-enable)."
fi

token_len=0

# Pre-export token ASAP so validate_token/auth_health can call kite_client.ensure()
if [[ -f "$TOKEN_PATH" ]]; then
  export KITE_ACCESS_TOKEN="$(tr -d ' \n\r\t' < "$TOKEN_PATH")"
  token_len="${#KITE_ACCESS_TOKEN}"

  if [[ "$token_len" -lt 20 ]]; then
    echo "[RUN_LIVE][WARN] token_file_present_but_short path=$TOKEN_PATH len=$token_len"
    unset KITE_ACCESS_TOKEN || true
    token_len=0
  else
    echo "[RUN_LIVE] pre-exported KITE_ACCESS_TOKEN len=$token_len tail4=${KITE_ACCESS_TOKEN: -4}"
  fi
else
  echo "[RUN_LIVE][INFO] token_file_not_found path=$TOKEN_PATH"
fi

validate_token() {
  EXECUTION_MODE=LIVE TRADING_MODE=LIVE python - <<'PY'
from core.auth_health import get_kite_auth_health

payload = get_kite_auth_health(force=True)
auth_ok = bool(payload.get("ok"))
auth_state = str(payload.get("auth_state") or "").strip().upper()
user_id = str(payload.get("user_id") or "").strip()
if (not auth_ok) or auth_state != "OK" or not user_id:
    print(
        "[RUN_LIVE] Token invalid: "
        f"auth_state={auth_state or 'UNKNOWN'} "
        f"user_id_present={bool(user_id)} "
        f"error={payload.get('error')}"
    )
    raise SystemExit(12)
print(f"[RUN_LIVE] Token valid. user_id={user_id}")
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

  # Re-export (login may have written a new token)
  if [[ -f "$TOKEN_PATH" ]]; then
    export KITE_ACCESS_TOKEN="$(tr -d ' \n\r\t' < "$TOKEN_PATH")"
    token_len="${#KITE_ACCESS_TOKEN}"

    if [[ "$token_len" -lt 20 ]]; then
      echo "[RUN_LIVE][WARN] token_file_present_but_short_after_login path=$TOKEN_PATH len=$token_len"
      unset KITE_ACCESS_TOKEN || true
      token_len=0
    else
      echo "[RUN_LIVE] post-login-exported KITE_ACCESS_TOKEN len=$token_len tail4=${KITE_ACCESS_TOKEN: -4}"
    fi
  else
    echo "[RUN_LIVE][WARN] token_file_missing_after_login path=$TOKEN_PATH"
    unset KITE_ACCESS_TOKEN || true
    token_len=0
  fi
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
if ! validate_token; then
  startup_auth_reason="$(python - <<'PY'
from core.auth_health import get_kite_auth_health

payload = get_kite_auth_health(force=True)
print(str(payload.get("error") or payload.get("auth_state") or "auth_required").strip())
PY
)"
  publish_auth_blocked_startup_state "$startup_auth_reason"
  exit 12
fi

if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
  echo "[RUN_LIVE] --validate-only complete. Exiting."
  exit 0
fi

if [[ "$LOGIN_ONLY" -eq 1 ]]; then
  echo "[RUN_LIVE] --login-only complete. Exiting."
  exit 0
fi


# --- after validate_token and LOGIN_ONLY/VALIDATE_ONLY exits ---

# Export token into environment for this process and children (main.py)
if [[ ! -f "$TOKEN_PATH" ]]; then
  echo "[RUN_LIVE][FATAL] token_file_missing path=$TOKEN_PATH"
  exit 2
fi

export KITE_ACCESS_TOKEN="$(tr -d ' \n\r\t' < "$TOKEN_PATH")"

if [[ "${#KITE_ACCESS_TOKEN}" -lt 20 ]]; then
  echo "[RUN_LIVE][FATAL] token_file_empty path=$TOKEN_PATH"
  exit 2
fi

if [[ "${DRY_RUN:-false}" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee]?[Ss])$ ]]; then
  echo "[RUN_LIVE][FATAL] DRY_RUN=true is incompatible with live production startup."
  exit 2
fi

export TRADING_MODE="LIVE"
export EXECUTION_MODE="LIVE"
export LIVE_BROKER_ADAPTER_ACTIVE="${LIVE_BROKER_ADAPTER_ACTIVE:-1}"
if [[ "$READ_ONLY_OBSERVATION" -eq 1 ]]; then
  export TRADING_MODE=SIM
  export EXECUTION_MODE=SIM
  export TRADEBOT_MODE=SIM
  export LIVE_AUDIT_ONLY=1
  export TRADEBOT_READ_ONLY=true
  export LIVE_BROKER_ADAPTER_ACTIVE=0
  export ALLOW_LIVE_ORDERS=0
  export AUTO_TRADE=0
  export AUTO_ORDER=0
  export LIVE_TRADING_ENABLED=false
  export PAPER_TRADING_ENABLED=false
  export BROKER_WRITE_AUTHORITY=false
  export ORDER_AUTHORITY=false
  export PAPER_AUTHORIZED=false
  export LIVE_EXECUTION_AUTHORIZED=false
  export MANUAL_APPROVAL_REQUIRED=1
  echo "[RUN_LIVE] READ_ONLY_OBSERVATION enforced; order authority disabled."
fi
resolve_live_predictor_startup_mode

echo "[RUN_LIVE] exported KITE_ACCESS_TOKEN len=${#KITE_ACCESS_TOKEN} tail4=${KITE_ACCESS_TOKEN: -4}"
echo "[RUN_LIVE] forced runtime mode TRADING_MODE=$TRADING_MODE EXECUTION_MODE=$EXECUTION_MODE"
echo "[RUN_LIVE] forcing startup-safe predictor mode LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD=$LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD"

echo "[RUN_LIVE] Starting main.py ..."
exec python "$ROOT_DIR/main.py"
