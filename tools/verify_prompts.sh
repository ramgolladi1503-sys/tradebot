#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROMPT="${1:-help}"
DRY_RUN="${VERIFY_PROMPTS_DRY_RUN:-0}"

log() {
  printf "\n\033[1;34m==> %s\033[0m\n" "$1"
}

warn() {
  printf "\n\033[1;33m[warn]\033[0m %s\n" "$1"
}

run_cmd() {
  local title="$1"
  shift
  log "$title"
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

run_py() {
  local title="$1"
  local code="$2"
  log "$title"
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] python inline snippet\n'
    return 0
  fi
  VERIFY_PROMPTS_INLINE_PY="$code" python - <<'PY'
import os

exec(os.environ["VERIFY_PROMPTS_INLINE_PY"], {})
PY
}

ensure_file_notice() {
  local f="$1"
  [[ -f "$f" ]] || warn "Missing file: $f"
}

p1() {
  run_cmd "1) rg observability funnel" rg -n "pipeline_funnel|trade_lifecycle|observability" main.py core strategies tests
  run_cmd "1) pytest" pytest -x -vv -s tests/ -k "funnel or lifecycle or observability"
  ensure_file_notice ".runtime/observability/pipeline_funnel.json"
  ensure_file_notice ".runtime/observability/trade_lifecycle.jsonl"
  run_py "1) pipeline_funnel sanity" '
import json, pathlib
p = pathlib.Path(".runtime/observability/pipeline_funnel.json")
print("exists:", p.exists())
if p.exists():
    d = json.loads(p.read_text())
    for k in ["timestamp","universe","candidates","scored","ready","executable","emitted"]:
        print(k, "=", d.get(k))
'
}

p2() {
  run_cmd "2) rg main.py global suppressor fix" rg -n "run_readiness_check|BLOCKED|risk_halt|return|continue|break" main.py
  run_cmd "2) pytest" pytest -x -vv -s tests/ -k "readiness and global"
  run_py "2) main.py needle scan" '
from pathlib import Path
p = Path("main.py")
txt = p.read_text()
for needle in ["run_readiness_check", "BLOCKED", "risk_halt"]:
    print(f"\n== {needle} ==")
    for i, line in enumerate(txt.splitlines(), 1):
        if needle in line:
            print(i, line)
'
  run_py "2) pipeline_funnel dump" '
import json, pathlib
p = pathlib.Path(".runtime/observability/pipeline_funnel.json")
if p.exists():
    d = json.loads(p.read_text())
    print(d)
else:
    print("pipeline_funnel.json missing")
'
}

p3() {
  run_cmd "3) rg review_queue defang" rg -n "MISSING_ENTRY|permission_reason|final_action|entry_status|execution_entry|display_entry|blockers" core/review_queue.py tests
  run_cmd "3) pytest" pytest -x -vv -s tests/ -k "review_queue or parity"
  run_py "3) suggestions spot check" '
import json, pathlib
p = pathlib.Path(".runtime/logs/suggestions.jsonl")
print("exists:", p.exists())
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-10:]:
        print({
            "trade_id": r.get("trade_id"),
            "permission": r.get("permission"),
            "readiness": r.get("readiness"),
            "final_action": r.get("final_action"),
            "entry_status": r.get("entry_status"),
            "execution_entry": r.get("execution_entry"),
            "display_entry": r.get("display_entry"),
            "blockers": r.get("blockers"),
        })
'
}

p4() {
  run_cmd "4) rg dashboard read-only" rg -n "permission_reason|final_action|entry_status|display_entry|execution_entry|blockers|readiness" dashboard/utils.py dashboard/streamlit_app_runtime.py tests
  run_cmd "4) pytest" pytest -x -vv -s tests/ -k "dashboard and readonly"
  warn "Manual step: streamlit run dashboard/streamlit_app.py"
  warn "Manual step: tail -f logs/streamlit.log"
}

p5() {
  run_cmd "5) rg unified trade-state machine" rg -n "idea_created|scored|ranked|advisory|execution_pending|partially_filled|active|exit_pending|closed|reconciled" core tests
  run_cmd "5) pytest" pytest -x -vv -s tests/ -k "trade_state_machine"
  run_py "5) trade_lifecycle tail" '
import json, pathlib
p = pathlib.Path(".runtime/observability/trade_lifecycle.jsonl")
print("exists:", p.exists())
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-20:]:
        print(r.get("trade_id"), r.get("stage"), r.get("status"), r.get("reason"))
'
}

p6() {
  run_cmd "6) rg blocker reclassification" rg -n "hard_block|soft_penalt|warning|stale|quote missing|depth missing|bid/ask|spread|premium_out_of_band|instrument_token_missing|confidence" strategies/trade_builder.py tests
  run_cmd "6) pytest" pytest -x -vv -s tests/ -k "trade_builder and blocker"
  run_py "6) blocker classification spot check" '
import json, pathlib
p = pathlib.Path(".runtime/logs/suggestions.jsonl")
print("exists:", p.exists())
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-15:]:
        print({
            "trade_id": r.get("trade_id"),
            "hard_blockers": r.get("hard_blockers"),
            "soft_penalties": r.get("soft_penalties"),
            "warnings": r.get("warnings"),
            "final_action": r.get("final_action"),
        })
'
}

p7() {
  run_cmd "7) rg candidate generation vs execution feasibility" rg -n "candidate exists|execution feasibility|advisory-only|executable" strategies core tests
  run_cmd "7) pytest" pytest -x -vv -s tests/ -k "candidate and execution feasibility"
  run_py "7) funnel split sanity" '
import json, pathlib
p = pathlib.Path(".runtime/observability/pipeline_funnel.json")
print("exists:", p.exists())
if p.exists():
    d = json.loads(p.read_text())
    for k in ["candidates","scored","ready","executable","emitted"]:
        print(k, "=", d.get(k))
'
}

p8() {
  run_cmd "8) rg opportunity ranking" rg -n "rank_global|rank_within_symbol|opportunity_score|opportunity_bucket|ranking" core strategies tests
  run_cmd "8) pytest" pytest -x -vv -s tests/ -k "ranking"
  run_py "8) ranking spot check" '
import json, pathlib
p = pathlib.Path(".runtime/logs/suggestions.jsonl")
print("exists:", p.exists())
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-20:]:
        print({
            "trade_id": r.get("trade_id"),
            "symbol": r.get("symbol"),
            "rank_global": r.get("rank_global"),
            "rank_within_symbol": r.get("rank_within_symbol"),
            "opportunity_score": r.get("opportunity_score") or r.get("score_total"),
            "opportunity_bucket": r.get("opportunity_bucket"),
        })
'
}

p9() {
  run_cmd "9) rg top-N selection" rg -n "top_executable|top_advisory|top_n" core dashboard config tests
  run_cmd "9) pytest" pytest -x -vv -s tests/ -k "top_n or selection"
  run_py "9) funnel full dump" '
import json, pathlib
p = pathlib.Path(".runtime/observability/pipeline_funnel.json")
print("exists:", p.exists())
if p.exists():
    print(json.loads(p.read_text()))
'
}

p10() {
  run_cmd "10) rg opportunity breadth / strike ladder" rg -n "ATM|strike_offset|setup_family|expiry_bucket|strike ladder|mean-reversion|pullback|continuation" strategies core tests
  run_cmd "10) pytest" pytest -x -vv -s tests/ -k "strike or breadth or candidate pool"
  run_py "10) breadth spot check" '
import json, pathlib
p = pathlib.Path(".runtime/logs/suggestions.jsonl")
print("exists:", p.exists())
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-20:]:
        print({
            "symbol": r.get("symbol"),
            "strike": r.get("strike"),
            "strike_offset": r.get("strike_offset"),
            "setup_family": r.get("setup_family"),
            "expiry_bucket": r.get("expiry_bucket"),
        })
'
}

p11() {
  run_cmd "11) rg capital allocator / slot manager" rg -n "slot_id|allocation_reason|capital_assigned|size_multiplier_effective|max_slots|per-symbol|per-theme" core config tests
  run_cmd "11) pytest" pytest -x -vv -s tests/ -k "capital_allocator or allocation"
  run_py "11) allocator spot check" '
import json, pathlib
p = pathlib.Path(".runtime/logs/suggestions.jsonl")
print("exists:", p.exists())
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-20:]:
        print({
            "trade_id": r.get("trade_id"),
            "rank_global": r.get("rank_global"),
            "slot_id": r.get("slot_id"),
            "allocation_reason": r.get("allocation_reason"),
            "capital_assigned": r.get("capital_assigned"),
            "size_multiplier_effective": r.get("size_multiplier_effective"),
        })
'
}

p12() {
  run_cmd "12) rg dynamic thresholds" rg -n "threshold_base|threshold_effective|threshold_adjustment_reason|regime|liquidity|time of day" core strategies tests
  run_cmd "12) pytest" pytest -x -vv -s tests/ -k "threshold"
  run_py "12) threshold spot check" '
import json, pathlib
p = pathlib.Path(".runtime/logs/suggestions.jsonl")
print("exists:", p.exists())
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-15:]:
        print({
            "trade_id": r.get("trade_id"),
            "threshold_base": r.get("threshold_base"),
            "threshold_effective": r.get("threshold_effective"),
            "threshold_adjustment_reason": r.get("threshold_adjustment_reason"),
        })
'
}

p13() {
  run_cmd "13) rg regime-specific strategy variants" rg -n "TRENDING_UP|TRENDING_DOWN|RANGE|VOLATILE|EXPIRY_CONTEXT|regime_router|expiry_context" strategies core tests
  run_cmd "13) pytest" pytest -x -vv -s tests/ -k "regime"
  run_py "13) regime spot check" '
import json, pathlib
p = pathlib.Path(".runtime/logs/suggestions.jsonl")
print("exists:", p.exists())
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-20:]:
        print({
            "symbol": r.get("symbol"),
            "strategy": r.get("strategy") or r.get("strategy_name"),
            "regime": r.get("regime"),
            "expiry_context": r.get("expiry_context"),
            "setup_family": r.get("setup_family"),
        })
'
}

p14() {
  run_cmd "14) rg system anomaly guard" rg -n "detect_anomalies|candidate_pool_size|advisory_count|size_multiplier|score_distribution|anomaly" core tests
  run_cmd "14) pytest" pytest -x -vv -s tests/ -k "anomaly_guard or anomaly"
  run_py "14) anomaly guard quick checks" '
from core.system_anomaly_guard import detect_anomalies
print(detect_anomalies({
    "feed_healthy": True,
    "market_open": True,
    "candidate_pool_size": 0,
    "advisory_count": 0,
    "size_multiplier_avg": 0.0,
}))
print(detect_anomalies({
    "feed_healthy": True,
    "market_open": True,
    "candidate_pool_size": 200,
    "advisory_count": 1,
    "size_multiplier_avg": 2.5,
}))
'
}

p15() {
  run_cmd "15) rg replay engine" rg -n "class ReplayEngine|def replay_session|def replay_tick|def load_artifacts" core scripts tests
  run_cmd "15) pytest" pytest -x -vv -s tests/ -k "replay_engine"
  warn 'Manual run:
python scripts/replay_session.py --symbol NIFTY --from-artifacts .runtime/logs --start "2026-03-12T09:15:00" --end "2026-03-12T10:00:00"
python scripts/replay_session.py --symbol BANKNIFTY --from-artifacts .runtime/logs --start "2026-03-12T09:15:00" --end "2026-03-12T10:00:00"'
}

p16() {
  run_cmd "16) rg research/evaluation layer" rg -n "compute_expectancy|analyze_regime_performance|analyze_time_buckets|group_by_setup|allocation_bucket" research tests
  run_cmd "16) pytest" pytest -x -vv -s tests/ -k "expectancy or regime_analysis or time_bucket"
  warn "Manual run: python research/setup_expectancy.py --input .runtime/logs/suggestions.jsonl"
  warn "Manual run: python research/regime_analysis.py --input .runtime/logs/suggestions.jsonl"
  warn "Manual run: python research/time_bucket_analysis.py --input .runtime/logs/suggestions.jsonl"
}

p17() {
  run_cmd "17) rg outcome labeling / post-trade truth" rg -n "favorable_excursion|adverse_excursion|blocked_falsely|blocked_correctly|skipped_by_allocator|poor_fill_quality|thesis_invalidated_quickly" core research tests
  run_cmd "17) pytest" pytest -x -vv -s tests/ -k "outcome_labels"
  run_py "17) outcome labels import" '
from core.outcome_labels import *
print("outcome labels import ok")
'
}

p18() {
  run_cmd "18) rg feature attribution" rg -n "analyze_feature_attribution|trend_alignment_score|momentum_score|liquidity_score|spread_score|regime_fit_score|freshness_score|reward_risk_score|allocation_priority_score" research tests
  run_cmd "18) pytest" pytest -x -vv -s tests/ -k "feature_attribution"
  warn "Manual run: python research/feature_attribution.py --input .runtime/logs/suggestions.jsonl"
}

p19() {
  run_cmd "19) rg execution realism" rg -n "estimate_slippage|choose_order_policy|assess_execution_quality|expected_slippage|spread_penalty|execution_ok" core tests
  run_cmd "19) pytest" pytest -x -vv -s tests/ -k "slippage_model or order_policy or execution_quality"
  run_py "19) slippage model sanity" '
from core.slippage_model import estimate_slippage
print(estimate_slippage({
    "ltp": 18.0,
    "bid": 17.5,
    "ask": 19.5,
    "spread": 2.0,
    "qty": 75,
}))
'
  run_py "19) order policy sanity" '
from core.order_policy import choose_order_policy
print(choose_order_policy({
    "bid": 72.0,
    "ask": 72.5,
    "spread": 0.5,
    "ltp": 72.25,
    "qty": 75,
    "liquidity_score": 0.9,
}))
print(choose_order_policy({
    "bid": 17.0,
    "ask": 21.0,
    "spread": 4.0,
    "ltp": 19.0,
    "qty": 75,
    "liquidity_score": 0.2,
}))
'
}

p20() {
  run_cmd "20) rg fill-quality calibration" rg -n "fill_quality_calibration|fill_quality_profile|expected_fill_deviation|slippage_multiplier|fill_confidence" core research tests
  run_cmd "20) pytest" pytest -x -vv -s tests/ -k "fill_quality"
  run_py "20) fill quality profile import" '
from core.fill_quality_profile import *
print("fill quality profile import ok")
'
  warn "Manual run: python research/fill_quality_calibration.py --input .runtime/logs/suggestions.jsonl"
}

p21() {
  run_cmd "21) rg observability dashboard" rg -n "candidate_pool_size|score_distribution|rejection_reason|blockers distribution|conversion rate|allocation summary" dashboard core tests
  run_cmd "21) pytest" pytest -x -vv -s tests/ -k "metrics_runtime or dashboard"
  warn "Manual step: streamlit run dashboard/streamlit_app.py"
  warn "Manual step: tail -f logs/streamlit.log"
}

p22() {
  run_cmd "22) rg reconciliation hardening" rg -n "reconcile_positions|reconcile_orders|restore_runtime_state|partial fill|delayed ack" core tests
  run_cmd "22) pytest" pytest -x -vv -s tests/ -k "reconciliation"
  run_py "22) reconciliation import" '
from core.reconciliation import *
print("reconciliation import ok")
'
}

p23() {
  run_cmd "23) rg strategy ablation / kill-switch" rg -n "strategy_ablation|advisory_only|throttle|contribution|expectancy" core config tests
  run_cmd "23) pytest" pytest -x -vv -s tests/ -k "strategy_ablation"
  run_py "23) strategy ablation import" '
from core.strategy_ablation import *
print("strategy ablation import ok")
'
}

p24() {
  run_cmd "24) rg portfolio optimizer" rg -n "optimize_portfolio|correlation|same-theme|exposure|diversification" core tests
  run_cmd "24) pytest" pytest -x -vv -s tests/ -k "portfolio_optimizer"
  run_py "24) portfolio optimizer sanity" '
from core.portfolio_optimizer import optimize_portfolio
candidates = [
    {"symbol":"NIFTY","direction":"LONG","score_total":0.86,"theme":"INDEX_CE"},
    {"symbol":"BANKNIFTY","direction":"LONG","score_total":0.84,"theme":"INDEX_CE"},
    {"symbol":"SENSEX","direction":"SHORT","score_total":0.74,"theme":"INDEX_PE"},
]
print(optimize_portfolio(candidates, current_positions=[]))
'
}

p25() {
  run_cmd "25) rg production rollout discipline" rg -n "feature_flag|shadow_mode|advisory_only|rollback|candidate_pipeline|ranking_engine|allocator|portfolio_optimizer|ml_ranking_hint|execution_realism|strategy_ablation" config core scripts tests
  run_cmd "25) pytest" pytest -x -vv -s tests/ -k "feature_flags or advisory_only or shadow_mode"
  run_py "25) config import" '
from config.config import *
print("config import ok")
'
  run_py "25) profile import" '
from config.profile import *
print("profile import ok")
'
  run_py "25) feed/runtime health" '
import json
from pathlib import Path
p = Path(".runtime/logs/feed_runtime_latest.json")
print("exists:", p.exists())
if p.exists():
    d = json.loads(p.read_text())
    for k in ["runtime_state","ws_connected","market_open"]:
        print(k, "=", d.get(k))
'
}

p26() {
  run_cmd "26) rg light ML ranking hints" rg -n "ranking_hint|train_ranking_hint|favorable_excursion_probability|realized_follow_through_hint|slippage_risk_hint" ml research tests
  run_cmd "26) pytest" pytest -x -vv -s tests/ -k "ranking_hint_model"
  warn "Manual run: python research/train_ranking_hint.py --input .runtime/logs/suggestions.jsonl"
}

master_code_presence() {
  run_cmd "MASTER) code presence" rg -n "pipeline_funnel|trade_lifecycle|trade_state_machine|rank_global|slot_id|threshold_effective|regime_router|detect_anomalies|ReplayEngine|compute_expectancy|outcome_labels|feature_attribution|estimate_slippage|fill_quality|metrics_runtime|reconcile_positions|strategy_ablation|optimize_portfolio|shadow_mode|ranking_hint" core dashboard strategies research ml config scripts tests
}

master_tests() {
  run_cmd "MASTER) full tests" pytest -x -vv -s tests/
}

master_advisory() {
  ensure_file_notice ".runtime/logs/suggestions.jsonl"
  if [[ -f ".runtime/logs/suggestions.jsonl" ]]; then
    run_cmd "MASTER) advisory tail" tail -n 20 .runtime/logs/suggestions.jsonl
  fi
  run_py "MASTER) advisory spot check" '
import json, pathlib
p = pathlib.Path(".runtime/logs/suggestions.jsonl")
if p.exists():
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows[-5:]:
        print({
            "symbol": r.get("symbol"),
            "strategy": r.get("strategy_name") or r.get("strategy"),
            "score_total": r.get("score_total") or r.get("opportunity_score"),
            "rank_global": r.get("rank_global"),
            "slot_id": r.get("slot_id"),
            "size_multiplier": r.get("size_multiplier") or r.get("size_multiplier_effective"),
            "blockers": r.get("blockers"),
            "candidate_pool_size": r.get("candidate_pool_size"),
        })
else:
    print("suggestions.jsonl missing")
'
}

master_feed() {
  run_py "MASTER) feed/runtime health" '
import json
from pathlib import Path
p = Path(".runtime/logs/feed_runtime_latest.json")
print("exists:", p.exists())
if p.exists():
    d = json.loads(p.read_text())
    for k in [
        "runtime_state",
        "ws_connected",
        "market_open",
        "last_tick_age_sec",
        "last_depth_age_sec",
        "subscribed_option_tokens_count",
    ]:
        print(k, "=", d.get(k))
'
}

master_dashboard() {
  warn "Manual step: streamlit run dashboard/streamlit_app.py"
  warn "Manual step: tail -f logs/streamlit.log"
}

block_core() {
  p1; p2; p3; p4; p5; p6; p7; p8; p9; p10
}

block_research() {
  p11; p12; p13; p14; p15; p16; p17; p18; p19; p20
}

block_prod() {
  p21; p22; p23; p24; p25; p26
}

master_all() {
  master_code_presence
  master_tests
  master_advisory
  master_feed
  master_dashboard
}

run_range() {
  local start="$1"
  local end="$2"
  local i
  for ((i=start; i<=end; i++)); do
    "p${i}"
  done
}

usage() {
  cat <<'EOF'
Usage:
  bash tools/verify_prompts.sh <target>

Targets:
  1 ... 26          Run one prompt verification
  1-5               Run a range
  core              Run prompts 1-10
  research          Run prompts 11-20
  prod              Run prompts 21-26
  master            Run master verification pack
  full              Run all 26 prompts, then master
  help              Show this message

Examples:
  bash tools/verify_prompts.sh 1
  bash tools/verify_prompts.sh 8
  bash tools/verify_prompts.sh 1-5
  bash tools/verify_prompts.sh core
  bash tools/verify_prompts.sh research
  bash tools/verify_prompts.sh prod
  bash tools/verify_prompts.sh master
  bash tools/verify_prompts.sh full

Environment:
  VERIFY_PROMPTS_DRY_RUN=1   Print the dispatched commands without executing them.
EOF
}

case "$PROMPT" in
  1) p1 ;;
  2) p2 ;;
  3) p3 ;;
  4) p4 ;;
  5) p5 ;;
  6) p6 ;;
  7) p7 ;;
  8) p8 ;;
  9) p9 ;;
  10) p10 ;;
  11) p11 ;;
  12) p12 ;;
  13) p13 ;;
  14) p14 ;;
  15) p15 ;;
  16) p16 ;;
  17) p17 ;;
  18) p18 ;;
  19) p19 ;;
  20) p20 ;;
  21) p21 ;;
  22) p22 ;;
  23) p23 ;;
  24) p24 ;;
  25) p25 ;;
  26) p26 ;;
  core) block_core ;;
  research) block_research ;;
  prod) block_prod ;;
  master) master_all ;;
  full)
    block_core
    block_research
    block_prod
    master_all
    ;;
  *-*)
    IFS='-' read -r start end <<< "$PROMPT"
    [[ "$start" =~ ^[0-9]+$ && "$end" =~ ^[0-9]+$ ]] || { usage; exit 1; }
    (( start >= 1 && end <= 26 && start <= end )) || { usage; exit 1; }
    run_range "$start" "$end"
    ;;
  help|--help|-h|"")
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
