#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"
export DATA_ROOT="${DATA_ROOT:-$ROOT_DIR/.runtime}"
export DESKS_ROOT="${DESKS_ROOT:-$DATA_ROOT/desks}"
export LOGS_ROOT="${LOGS_ROOT:-$DATA_ROOT/logs}"
export REPORTS_ROOT="${REPORTS_ROOT:-$DATA_ROOT/reports}"
export LOCKS_ROOT="${LOCKS_ROOT:-$DATA_ROOT/locks}"
export DB_ROOT="${DB_ROOT:-$DATA_ROOT/db}"

ensure_runtime_dirs() {
  local d=""
  for d in "$DATA_ROOT" "$DESKS_ROOT" "$LOGS_ROOT" "$REPORTS_ROOT" "$LOCKS_ROOT" "$DB_ROOT" "$ROOT_DIR/.runtime"; do
    if ! mkdir -p "$d" 2>/dev/null; then
      echo "[RUN_LIVE_SAFE][ERROR] runtime_dir_not_writable path=$d"
      exit 2
    fi
  done
}

echo "[RUN_LIVE_SAFE] Project: ${ROOT_DIR}"
ensure_runtime_dirs

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
    echo "[RUN_LIVE_SAFE] OpenMP runtime path configured: $selected_dir (py_arch=$py_arch)"
    return 0
  fi

  if [[ "$checked_any" -eq 1 ]]; then
    echo "[RUN_LIVE_SAFE][WARN] libomp found but architecture mismatched for py_arch=$py_arch; xgboost may run in degraded mode."
  else
    echo "[RUN_LIVE_SAFE][WARN] libomp.dylib not found; xgboost may run in degraded mode."
  fi
  if [[ -n "${CONDA_PREFIX:-}" ]]; then
    echo "[RUN_LIVE_SAFE][HINT] Install ARM-compatible runtime in conda:"
    echo "  conda install -n ${CONDA_DEFAULT_ENV:-tradebot} -c conda-forge llvm-openmp py-xgboost"
  fi
  return 0
}

configure_openmp_runtime
set +e
python "${ROOT_DIR}/scripts/check_kite_auth.py" --mode LIVE
status=$?
set -e

if [[ "$status" -eq 2 ]]; then
  echo "[RUN_LIVE_SAFE] Another LIVE/PAPER process already owns the Kite session lock."
  exit 2
fi

if [[ "$status" -eq 4 ]]; then
  echo "[RUN_LIVE_SAFE] Unable to create/open instance lock at .runtime/locks/kite_session.lock"
  exit 2
fi

if [[ "$status" -ne 0 ]]; then
  echo "[RUN_LIVE_SAFE] Kite auth is not healthy. Reauthenticate first:"
  echo "  python scripts/kite_autologin_localhost.py"
  echo "  python scripts/check_kite_auth.py --mode LIVE"
  exit 1
fi

echo "[RUN_LIVE_SAFE] Auth OK. Starting main.py ..."
python "${ROOT_DIR}/main.py"
