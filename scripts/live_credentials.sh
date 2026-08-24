#!/usr/bin/env bash
# Source only from run_live.sh. Values are never printed or persisted.
set -euo pipefail

credential_file="${TRADEBOT_KITE_CREDENTIAL_FILE:-${HOME}/.tradebot/credentials/kite_app.env}"
if [[ ! -f "$credential_file" || ! -r "$credential_file" ]]; then
  return 0
fi

if [[ "$(stat -f '%Lp' "$credential_file" 2>/dev/null || echo 000)" != "600" ]]; then
  echo "[RUN_LIVE][ERROR] credential_file_permissions_must_be_0600" >&2
  return 1
fi

while IFS='=' read -r key value; do
  [[ -z "${key//[[:space:]]/}" || "$key" == \#* ]] && continue
  case "$key" in
    KITE_API_KEY|KITE_API_SECRET)
      [[ "$value" != *[[:space:]]* ]] || { echo "[RUN_LIVE][ERROR] credential_format_invalid" >&2; return 1; }
      printf -v "$key" '%s' "$value"
      export "$key"
      ;;
    *)
      echo "[RUN_LIVE][ERROR] credential_file_contains_unapproved_key" >&2
      return 1
      ;;
  esac
done < "$credential_file"

[[ -n "${KITE_API_KEY:-}" && -n "${KITE_API_SECRET:-}" ]]
