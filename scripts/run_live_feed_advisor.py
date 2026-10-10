"""Sentinel Live 1-Minute Candle Real-Time Paper Advisor.

Fetches live completed 1m candles directly from Upstox intraday endpoint
while live chunk ticks are capturing in the background.
Evaluates:
- 09:15-09:45 Opening Shock Range
- VWAP & Rejection Wicks
- Dynamic Slippage Veto Gate
- Real-time CE/PE paper triggers
"""

import time
import json
import math
import urllib.request
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
from core.nse_fo_contract_master import (
    NSEContractMasterError,
    load_verified_capture_authority,
)

from core.model_manifest_generator import SentinelManifestLock
from core.dynamic_slippage_model import DynamicOptionSlippageModel
from core.expiry_calendar import get_days_to_expiry, is_holiday
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_EXIT_PENDING,
    STATE_LIQUIDATED
)


def _normalize_expiry_label(value: Any) -> Optional[str]:
    """Normalize an explicit date or NSE-style instrument expiry label."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    for fmt in ("%d %b %y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d %b %y").upper()
        except ValueError:
            continue
    return None


class SentinelLiveFeedAdvisor:
    def __init__(
        self,
        artifacts_dir: str = "artifacts",
        ticker: str = "NIFTY",
        target_expiry: Optional[str] = None
    ):
        self.lock_mgr = SentinelManifestLock(artifact_directory=artifacts_dir)
        if not self.lock_mgr.verify_manifest_or_fail_closed():
            raise SystemExit("ABORT: Model manifest verification failed.")

        with open(Path(artifacts_dir) / "calibrated_regime_matrix.json") as f:
            self.calib = json.load(f)

        self.ticker = ticker.upper()
        self.target_expiry = str(target_expiry).strip().upper() if target_expiry else None
        self.slippage = DynamicOptionSlippageModel(base_brokerage_pts=0.40)
        self.apm = ActivePositionManager()
        self.spread_threshold = 0.04
        self.or_high = -1e9
        self.or_low = 1e9
        self.shock_active = True
        self.last_evaluated_bar = None
        self.session_ker = None
        self.ewma_ker = 0.5
        self.ker_persistence_count = 0
        self.last_exit_price = None
        self.last_exit_direction = None

        # Append-Only Audit Sink Setup
        today_str = datetime.now().strftime("%Y%m%d")
        self.audit_log_path = Path(f"runtime/audit/sentinel_execution_paths_{today_str}.jsonl")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate unique run ID and write immutable startup manifest
        import os, uuid, subprocess, hashlib
        self.run_id = f"sentinel-{today_str}-{uuid.uuid4().hex[:8]}"
        self.pid = os.getpid()
        self.git_sha = "UNKNOWN"
        self.dirty_worktree = None
        provenance_errors = []
        try:
            sha_out = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
            if sha_out:
                self.git_sha = sha_out
            diff_out = subprocess.check_output(["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
            self.dirty_worktree = bool(diff_out)
        except Exception as exc:
            provenance_errors.append(f"git_provenance_error: {type(exc).__name__}: {exc}")

        # Compute runtime config hash from calib
        calib_bytes = json.dumps(self.calib, sort_keys=True).encode("utf-8")
        self.config_hash = hashlib.sha256(calib_bytes).hexdigest()

        # Check for input capture parquet sources (chunks and full parquets) and hash them via streaming reads
        data_artifacts = {}
        for root_dir in [
            Path(".runtime/market_data"),
            Path("runtime/market_data"),
            Path("/Volumes/TradeBot/live market capture"),
            Path("/Volumes/TradeBotData/live market capture"),
        ]:
            date_dir = root_dir / datetime.now().strftime("%Y-%m-%d")
            if date_dir.exists():
                candidate_files = list(date_dir.glob("chunks/*.parquet")) + list(date_dir.glob("*.parquet"))
                for pq_file in sorted(set(candidate_files)):
                    try:
                        hasher = hashlib.sha256()
                        with open(pq_file, "rb") as pf:
                            while chunk := pf.read(65536):
                                hasher.update(chunk)
                        data_artifacts[str(pq_file)] = hasher.hexdigest()
                    except Exception as exc:
                        data_artifacts[str(pq_file)] = f"HASH_ERROR: {type(exc).__name__}: {exc}"
        if not data_artifacts:
            data_artifacts["status"] = "SOURCE_PATHS_UNCONFIGURED_OR_ABSENT_AT_STARTUP"

        # Emit startup manifest if not already present
        self.manifest_path = Path(f"runtime/audit/sentinel_manifest_{self.run_id}.json")
        try:
            manifest_payload = {
                "run_id": self.run_id,
                "pid": self.pid,
                "start_time_iso": datetime.now().isoformat(),
                "git_sha": self.git_sha,
                "dirty_worktree": self.dirty_worktree,
                "provenance_errors": provenance_errors,
                "config_hash": self.config_hash,
                "ticker": self.ticker,
                "target_expiry": self.target_expiry,
                "execution_mode": "CAPTURE_RECEIVE_TIME_REPLAY_ONLY",
                "receive_time_verified": True,
                "exchange_event_time_verified": False,
                "data_artifacts": data_artifacts,
                "data_artifacts_scope": "best_effort_files_observed_at_startup_not_a_completeness_claim",
            }
            with open(self.manifest_path, "w", encoding="utf-8") as mf:
                json.dump(manifest_payload, mf, indent=2)
        except Exception as exc:
            raise RuntimeError(f"Unable to write startup provenance manifest {self.manifest_path}: {exc}") from exc

        # Expiry Calendar State Check:
        # TUESDAY = NIFTY (0-DTE), THURSDAY = SENSEX (0-DTE)
        now_dt = datetime.now()
        self.dte = get_days_to_expiry(now_dt, self.ticker)
        self.is_expiry_day = (self.dte == 0)
        print(f"📅 [EXPIRY CALENDAR AUDIT] Asset: {self.ticker} | DTE: {self.dte} | Is Expiry Day (0-DTE): {self.is_expiry_day}")
        print(f"   (Schedule Rules: Tuesday = NIFTY Expiry, Thursday = SENSEX Expiry)")
        print(f"📝 [AUDIT LOG SINK] Streaming to: {self.audit_log_path} (Run ID: {self.run_id})")

    def fetch_live_1m_candles(self) -> list:
        url = "https://api.upstox.com/v2/historical-candle/intraday/NSE_INDEX%7CNifty%2050/1minute"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "TradeBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            candles = data.get("data", {}).get("candles", [])
            return sorted(candles, key=lambda x: x[0])

    def resolve_real_option_quote(
        self,
        strike: int,
        opt_type: str,
        expiry: Optional[str] = None,
        decision_cutoff_epoch: Optional[float] = None
    ) -> Optional[dict]:
        """Resolve a quote only from ticks bound to a re-verified NSE/Upstox manifest."""
        import glob
        from zoneinfo import ZoneInfo
        today_date_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        chunk_patterns = [
            f".runtime/market_data/{today_date_str}/chunks/*.parquet",
            f"runtime/market_data/{today_date_str}/chunks/*.parquet",
            f"/Volumes/TradeBot/live market capture/{today_date_str}/chunks/*.parquet",
            f"/Volumes/TradeBotData/live market capture/{today_date_str}/chunks/*.parquet",
        ]
        chunks = []
        for pat in chunk_patterns:
            chunks.extend(glob.glob(pat))
        if not chunks:
            return None
        try:
            capture_dirs: dict[Path, list[str]] = {}
            for chunk in set(chunks):
                capture_dirs.setdefault(Path(chunk).parent.parent, []).append(chunk)
            newest_chunk_names = {
                capture_dir: max(Path(chunk).name for chunk in values)
                for capture_dir, values in capture_dirs.items()
            }
            newest_name = max(newest_chunk_names.values())
            newest_dirs = [path for path, name in newest_chunk_names.items() if name == newest_name]
            if len(newest_dirs) != 1:
                return None
            daily_dir = newest_dirs[0]
            same_capture_chunks = capture_dirs[daily_dir]
            latest_chunk = max(same_capture_chunks, key=lambda value: Path(value).name)
            frames = [pd.read_parquet(path) for path in sorted(same_capture_chunks)]
            if not frames:
                return None
            df = pd.concat(frames, ignore_index=True)
            authority_hashes = (
                df["contract_authority_manifest_sha256"].dropna().astype(str).str.strip().unique().tolist()
                if "contract_authority_manifest_sha256" in df.columns else []
            )
            authority_hashes = [value for value in authority_hashes if value]
            if len(authority_hashes) != 1:
                return None
            authority = load_verified_capture_authority(Path(latest_chunk).parent.parent, authority_hashes[0])
            return self.resolve_quote_from_dataframe(
                df=df,
                strike=strike,
                opt_type=opt_type,
                expiry=expiry,
                decision_cutoff_epoch=decision_cutoff_epoch,
                contract_authority=authority,
            )
        except (OSError, ValueError, NSEContractMasterError):
            return None

    def resolve_quote_from_dataframe(
        self,
        df: pd.DataFrame,
        strike: int,
        opt_type: str,
        expiry: Optional[str] = None,
        decision_cutoff_epoch: Optional[float] = None,
        contract_authority=None,
    ) -> Optional[dict]:
        """Extract a quote only when token, symbol, contract tuple, and source hashes bind."""
        ticker = getattr(self, "ticker", "NIFTY").upper()
        explicit_expiry = expiry if expiry is not None else getattr(self, "target_expiry", None)
        if contract_authority is None:
            contract_authority = getattr(self, "contract_authority", None)
        if contract_authority is None:
            return None

        try:
            if "ts" not in df.columns:
                return None
            capture_ts = pd.to_numeric(df["ts"], errors="coerce")
            if capture_ts.empty or capture_ts.isna().any() or not capture_ts.map(math.isfinite).all():
                return None
            df = df.copy()
            df["ts"] = capture_ts
            if decision_cutoff_epoch is not None:
                cutoff = float(decision_cutoff_epoch)
                if not math.isfinite(cutoff):
                    return None
                df = df.loc[df["ts"] <= cutoff].copy()
        except (TypeError, ValueError, OverflowError):
            return None
        if decision_cutoff_epoch is not None:
            if df.empty:
                return None

        required = {"symbol", "token", "contract_authority_manifest_sha256"}
        if not required.issubset(df.columns):
            return None
        frame_hashes = df["contract_authority_manifest_sha256"].dropna().astype(str).str.strip().unique().tolist()
        frame_hashes = [value for value in frame_hashes if value]
        if frame_hashes != [contract_authority.manifest_sha256]:
            return None
        df = df.loc[
            df["contract_authority_manifest_sha256"].fillna("").astype(str).str.strip()
            == contract_authority.manifest_sha256
        ].copy()
        if df.empty:
            return None

        expected_symbol = None
        expected_entry = None
        for instrument_key, entry in contract_authority.selected_by_instrument_key.items():
            try:
                entry_expiry = date.fromisoformat(str(entry.get("expiry")))
                entry_matches_request = (
                    entry.get("underlying") == ticker
                    and entry.get("option_type") == str(opt_type).upper()
                    and float(entry.get("strike")) == float(strike)
                    and (
                        explicit_expiry is None
                        or _normalize_expiry_label(explicit_expiry)
                        == _normalize_expiry_label(entry_expiry.isoformat())
                    )
                )
            except (TypeError, ValueError, OverflowError):
                return None
            if entry_matches_request:
                if expected_entry is not None:
                    return None
                expected_entry = entry
                expected_symbol = str(entry.get("upstox_trading_symbol", ""))
        if expected_entry is None or not expected_symbol:
            return None
        same_symbol_rows = df.loc[df["symbol"].astype(str).str.strip() == expected_symbol]
        same_symbol_tokens = same_symbol_rows["token"].dropna().astype(str).str.strip().unique().tolist()
        if same_symbol_rows.empty or same_symbol_tokens != [str(expected_entry.get("upstox_instrument_key", ""))]:
            return None

        matches = []
        contract_entry = None
        for _, row in df.iterrows():
            token = str(row.get("token", "")).strip()
            symbol = str(row.get("symbol", "")).strip()
            entry = contract_authority.selected_by_instrument_key.get(token)
            if entry is None or entry.get("upstox_trading_symbol") != symbol:
                continue
            if entry.get("underlying") != ticker or entry.get("option_type") != str(opt_type).upper():
                continue
            try:
                if float(entry.get("strike")) != float(strike):
                    continue
                resolved_expiry = date.fromisoformat(str(entry.get("expiry")))
                if explicit_expiry is not None:
                    normalized_expiry = _normalize_expiry_label(explicit_expiry)
                    if normalized_expiry is None:
                        return None
                    if _normalize_expiry_label(resolved_expiry.isoformat()) != normalized_expiry:
                        continue
                verified_entry = contract_authority.verify_candidate(
                    instrument_key=token,
                    symbol=symbol,
                    underlying=ticker,
                    expiry=resolved_expiry,
                    strike=strike,
                    option_type=opt_type,
                )
            except (TypeError, ValueError, OverflowError):
                return None
            if verified_entry is None:
                continue
            matches.append(row)
            contract_entry = verified_entry

        if not matches or contract_entry is None:
            return None
        matches = pd.DataFrame(matches)
        exp_str = _normalize_expiry_label(contract_entry.get("expiry"))
        if exp_str is None:
            return None

        # Sort by timestamp and extract the latest quote row
        if matches["token"].astype(str).str.strip().nunique() != 1:
            return None
        last_row = matches.sort_values("ts", kind="stable").iloc[-1]
        
        tok = str(last_row["token"]).strip() if pd.notna(last_row["token"]) else ""
        if not tok:
            return None

        try:
            ltp = float(last_row["ltp"])
            bid = float(last_row["bid"])
            ask = float(last_row["ask"])
            volume = float(last_row["vol"])
            open_interest = float(last_row["oi"])
            capture_timestamp = float(last_row["ts"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return None

        # Basic structural sanity check
        if not all(math.isfinite(value) for value in (ltp, bid, ask, volume, open_interest, capture_timestamp)):
            return None
        if ltp <= 0 or bid <= 0 or ask <= 0:
            return None

        # Inverted / crossed book is structurally invalid
        if bid > ask:
            return None

        res = {
            "symbol": str(last_row["symbol"]),
            "token": tok,
            "ltp": ltp,
            "bid": bid,
            "ask": ask,
            "vol": volume,
            "oi": open_interest,
            "timestamp": capture_timestamp,
            "expiry": exp_str,
            "expiry_source": "NSE_FO_MII_CONTRACT_MASTER",
            "contract_key": contract_entry["contract_key"],
            "contract_authority_manifest_sha256": contract_authority.manifest_sha256,
            "nse_contract_id": contract_entry["nse_instrument_id"],
            "nse_contract_file": contract_authority.nse_metadata["artifact_filename"],
            "nse_contract_source": contract_authority.nse_metadata["file_url"],
            "nse_contract_trading_date": contract_authority.nse_metadata["trading_date"],
            "nse_report_current_date": contract_authority.nse_metadata["report_current_date"],
            "nse_report_future_date": contract_authority.nse_metadata["report_future_date"],
            "nse_contract_schema_version": contract_authority.nse_metadata["schema_version"],
            "nse_contract_file_sha256": contract_authority.nse_metadata["file_sha256"],
            "upstox_master_file": contract_authority.upstox_metadata["artifact_filename"],
            "upstox_master_source": contract_authority.upstox_metadata["source_url"],
            "upstox_master_downloaded_at_utc": contract_authority.upstox_metadata["downloaded_at_utc"],
            "upstox_master_sha256": contract_authority.upstox_metadata["sha256"],
        }
        return res

    def evaluate_option_candidate(
        self,
        entry_dir: Optional[str],
        chosen_strike: Optional[int],
        contract_choice: Optional[str],
        signal_display: str,
        bar_close_cutoff_epoch: float,
        spot_close: float,
        bar_time_str: str,
        sl_pts: float,
        target_pts: float,
        total_drag_pts: float,
        current_gear: str,
        btime: dtime
    ) -> dict:
        """Evaluates descriptive option candidate observation and preserves separate paper APM lifecycle.

        1. If entry_dir is present:
           - Resolves option quote at or before completed-bar boundary.
           - If quote is uniquely resolved and uncrossed:
             * Emits descriptive option_candidate observation (CAPTURE_RECEIVE_TIME_REPLAY_ONLY).
             * If APM is in STANDBY/LIQUIDATED, executes existing paper position entry via arm_and_enter.
           - If quote is missing, ambiguous, or crossed:
             * Retains underlying directional signal in advisory.
             * Emits candidate_status=NOT_EVALUABLE with explicit reason.
             * Does NOT arm APM; APM state remains unchanged.
        """
        option_candidate = None
        candidate_status = "NONE"
        candidate_reason = None
        risk_flag = "NORMAL"

        if not entry_dir:
            return {
                "signal_display": signal_display,
                "risk_flag": risk_flag,
                "candidate_status": candidate_status,
                "candidate_reason": candidate_reason,
                "option_candidate": option_candidate,
            }

        # Resolve captured option quote at the completed-bar boundary.
        opt_q = self.resolve_real_option_quote(
            chosen_strike,
            entry_dir,
            decision_cutoff_epoch=bar_close_cutoff_epoch
        )

        if opt_q:
            # Descriptive capture/receive-time observation only; exchange timestamp is unverified.
            candidate_status = "CAPTURE_RECEIVE_TIME_REPLAY_ONLY"
            option_candidate = {
                "contract": str(opt_q.get("symbol")),
                "token": str(opt_q.get("token")),
                "expiry": opt_q.get("expiry"),
                "expiry_source": opt_q.get("expiry_source"),
                "contract_key": opt_q.get("contract_key"),
                "contract_authority_manifest_sha256": opt_q.get("contract_authority_manifest_sha256"),
                "nse_contract_id": opt_q.get("nse_contract_id"),
                "nse_contract_file": opt_q.get("nse_contract_file"),
                "nse_contract_source": opt_q.get("nse_contract_source"),
                "nse_contract_trading_date": opt_q.get("nse_contract_trading_date"),
                "nse_report_current_date": opt_q.get("nse_report_current_date"),
                "nse_report_future_date": opt_q.get("nse_report_future_date"),
                "nse_contract_schema_version": opt_q.get("nse_contract_schema_version"),
                "nse_contract_file_sha256": opt_q.get("nse_contract_file_sha256"),
                "upstox_master_file": opt_q.get("upstox_master_file"),
                "upstox_master_source": opt_q.get("upstox_master_source"),
                "upstox_master_downloaded_at_utc": opt_q.get("upstox_master_downloaded_at_utc"),
                "upstox_master_sha256": opt_q.get("upstox_master_sha256"),
                "direction": entry_dir,
                "strike": chosen_strike,
                "source_capture_ts": opt_q.get("timestamp"),
                "capture_time_basis": "WEBSOCKET_ON_MESSAGE_CALLBACK_TIME",
                "exchange_event_time_verified": False,
                "observed_ltp": opt_q.get("ltp"),
                "observed_bid": opt_q.get("bid"),
                "observed_ask": opt_q.get("ask"),
                "status": "CAPTURE_RECEIVE_TIME_REPLAY_ONLY",
                "receive_time_verified": True,
            }
            signal_display = f"{signal_display} | [CAPTURE_RECEIVE_TIME_REPLAY_OBSERVATION] {opt_q.get('symbol')} LTP: ₹{opt_q.get('ltp'):.2f}"

            # Preserve established separate paper APM state machine entry
            if self.apm.state in {STATE_STANDBY, STATE_LIQUIDATED}:
                pos_id = f"TRADE_{btime.strftime('%H%M')}_{entry_dir}"
                is_runner = (current_gear == "GEAR_2_TREND")
                opt_sl_pct = 0.20 if (current_gear == "GEAR_2_TREND") else None
                self.apm.arm_and_enter(
                    position_id=pos_id,
                    direction=entry_dir,
                    contract=contract_choice,
                    entry_price=spot_close,
                    entry_time_str=bar_time_str,
                    sl_pts=sl_pts,
                    tp_pts=target_pts,
                    friction_drag_pts=total_drag_pts,
                    opt_quote=opt_q,
                    is_runner_mode=is_runner,
                    session_gear=current_gear,
                    opt_stop_loss_pct=opt_sl_pct
                )
                risk_flag = "EXECUTED_IN_FLIGHT"
                opt_quote_str = f" | Option LTP: ₹{opt_q['ltp']:.2f} (Bid: ₹{opt_q['bid']:.2f} Ask: ₹{opt_q['ask']:.2f})"
                runner_tag = f" [{current_gear} | RUNNER 50/50 | OPT-SL -20%]" if is_runner else f" [{current_gear} | SCALP 15M]"
                print(f"🚀 [NEW POSITION OPENED] {pos_id} | {contract_choice} @ Spot {spot_close:.2f} | SL: {spot_close - sl_pts if entry_dir == 'CE' else spot_close + sl_pts:.1f} | TP: {spot_close + target_pts if entry_dir == 'CE' else spot_close - target_pts:.1f}{runner_tag}{opt_quote_str}")
            else:
                risk_flag = "OBSERVED_CAPTURE_RECEIVE_TIME_REPLAY"
        else:
            # Contract identity ambiguous or pre-boundary quote absent: keep directional signal, expose NOT_EVALUABLE
            candidate_status = "NOT_EVALUABLE"
            candidate_reason = "Unresolved contract identity or missing pre-boundary captured quote"
            signal_display = f"{signal_display} -> OPTION_QUOTE_NOT_EVALUABLE ({candidate_reason})"
            risk_flag = "VETO_OPTION_QUOTE_NOT_EVALUABLE"

        return {
            "signal_display": signal_display,
            "risk_flag": risk_flag,
            "candidate_status": candidate_status,
            "candidate_reason": candidate_reason,
            "option_candidate": option_candidate,
        }

    def evaluate_entry_gates(
        self,
        entry_dir: Optional[str],
        signal_display: str,
        in_lunch_dead_zone: bool,
        is_counter_trend_fade: bool,
        can_enter_energy: bool,
        e_atr_rem: float,
        req_energy: float,
        insufficient_displacement: bool,
        atr_1m: float,
        atr_extension_exhausted: bool,
        session_range: float,
        spread_ratio: float,
        chosen_strike: Optional[int],
        contract_choice: Optional[str],
        bar_close_cutoff_epoch: float,
        spot_close: float,
        bar_time_str: str,
        sl_pts: float,
        target_pts: float,
        total_drag_pts: float,
        current_gear: str,
        btime: dtime
    ) -> dict:
        """Evaluates ordered risk gates and delegates to evaluate_option_candidate only if unvetoed.

        Ordered veto precedence:
        1. Lunch dead zone freeze
        2. Trend purity / counter-trend fade
        3. Energy depletion
        4. Insufficient displacement re-entry
        5. Macro ATR extension exhaustion
        6. Spread expansion
        7. If clear, evaluate option candidate and preserve paper APM lifecycle
        """
        risk_flag = "NORMAL"
        option_candidate = None
        candidate_status = "NONE"
        candidate_reason = None

        if in_lunch_dead_zone and entry_dir:
            signal_display = f"☕ [LUNCH FREEZE VETO] {signal_display} -> SUPPRESSED (Gear 1 Range Dead-Zone 11:00-13:30 PM)"
            risk_flag = "VETO_LUNCH_DEAD_ZONE"
        elif is_counter_trend_fade and entry_dir:
            signal_display = f"🚫 [TREND PURITY VETO] {signal_display} -> SUPPRESSED (Forbid counter-trend fades on Gear 2 Trend day)"
            risk_flag = "VETO_COUNTER_TREND_FADE"
        elif not can_enter_energy and entry_dir:
            signal_display = f"🚫 [ENERGY GATE VETO] {signal_display} -> SUPPRESSED (Remaining ATR {e_atr_rem:.1f} < Required {req_energy:.1f})"
            risk_flag = "VETO_ENERGY_DEPLETED"
        elif insufficient_displacement and entry_dir:
            signal_display = f"🛑 [DISPLACEMENT VETO] {signal_display} -> SUPPRESSED (Re-entry requires >= {max(8.0, 1.0 * atr_1m):.1f}pts progress from prior exit {self.last_exit_price:.1f})"
            risk_flag = "VETO_INSUFFICIENT_DISPLACEMENT"
        elif atr_extension_exhausted and entry_dir and ("Breakout" in signal_display or "Breakdown" in signal_display):
            signal_display = f"🛑 [ATR EXTENSION VETO] {signal_display} -> SUPPRESSED (Session Range {session_range:.1f}pts > 300.0pts Exhaustion Cap)"
            risk_flag = "VETO_ATR_EXTENSION_EXHAUSTED"
        elif spread_ratio > self.spread_threshold and entry_dir:
            signal_display = f"🚨 [SPREAD VETO] {signal_display} -> SUPPRESSED (>4.0% spread)"
            risk_flag = "VETO_SPREAD_EXPANDED"
        elif entry_dir:
            eval_res = self.evaluate_option_candidate(
                entry_dir=entry_dir,
                chosen_strike=chosen_strike,
                contract_choice=contract_choice,
                signal_display=signal_display,
                bar_close_cutoff_epoch=bar_close_cutoff_epoch,
                spot_close=spot_close,
                bar_time_str=bar_time_str,
                sl_pts=sl_pts,
                target_pts=target_pts,
                total_drag_pts=total_drag_pts,
                current_gear=current_gear,
                btime=btime
            )
            signal_display = eval_res["signal_display"]
            risk_flag = eval_res["risk_flag"]
            candidate_status = eval_res["candidate_status"]
            candidate_reason = eval_res["candidate_reason"]
            option_candidate = eval_res["option_candidate"]

        return {
            "signal_display": signal_display,
            "risk_flag": risk_flag,
            "candidate_status": candidate_status,
            "candidate_reason": candidate_reason,
            "option_candidate": option_candidate,
        }

    def emit_and_append_audit_log(self, payload: dict):
        """Append one advisory audit row with explicit non-execution safety claims."""
        audit_row = dict(payload)
        audit_row.update({
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        })
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_row) + "\n")
        except IOError as e:
            print(f"🚨 [AUDIT LOG ERROR] Failed to write row: {e}")

    def compress_audit_log_to_parquet(self):
        """Sweeps today's .jsonl rows into Snappy-compressed Parquet at session close."""
        if not self.audit_log_path.exists() or self.audit_log_path.stat().st_size == 0:
            return
        try:
            records = []
            with open(self.audit_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            if records:
                df = pd.DataFrame(records)
                pq_path = self.audit_log_path.with_suffix(".parquet")
                df.to_parquet(pq_path, compression="snappy")
                print(f"🗜️ [AUDIT COMPRESSION COMPLETE] Saved {len(df):,} rows to {pq_path.name}")
        except Exception as e:
            print(f"🚨 [AUDIT COMPRESSION ERROR] {e}")

    def calibrate_morning_range(self, candles: list):
        """Processes historical morning bars (09:15-09:45) to calibrate Opening Range."""
        for c in candles:
            b_dt = datetime.fromisoformat(c[0])
            btime = b_dt.time()
            h, l = float(c[2]), float(c[3])
            if btime <= dtime(9, 45, 0):
                self.or_high = max(self.or_high, h)
                self.or_low = min(self.or_low, l)
        
        if self.or_high > -1e8 and self.or_low < 1e8:
            self.shock_active = False
            or_width = self.or_high - self.or_low
            print(f"🔓 [OPENING RANGE CALIBRATED] OR High: {self.or_high:.2f} | OR Low: {self.or_low:.2f} | Width: {or_width:.2f} pts")
            
            # Query Institutional Session Memory Bank for matching historical days
            try:
                from core.session_regime_memory import find_similar_sessions
                # Approximate morning efficiency ratio
                disp = abs(float(candles[-1][4]) - float(candles[0][1]))
                tot_p = sum(abs(float(candles[k][4]) - float(candles[k-1][4])) for k in range(1, len(candles)))
                approx_ker = disp / max(0.1, tot_p)
                matches = find_similar_sessions(current_ker=approx_ker, current_or_width=or_width, top_k=1)
                if matches:
                    m = matches[0]
                    print(f"🧠 [REGIME MEMORY RETRIEVAL] Matching Historical Session: {m['date']} (Regime: {m['classified_regime']}, KER: {m['ker_efficiency_ratio']})")
                    print(f"   💡 Historical Lesson: {m['key_lesson']}")
            except Exception as e:
                pass

    def run_loop(self):
        print("🛰️ [SENTINEL LIVE FEED ADVISOR ONLINE] Polling live completed 1m candles...")
        print("🛡️ [SLIPPAGE GATE ENGAGED] Spread Veto Threshold: 4.0%")

        # Initial calibration pass
        init_candles = self.fetch_live_1m_candles()
        if init_candles:
            self.calibrate_morning_range(init_candles)

        while True:
            try:
                candles = self.fetch_live_1m_candles()
                if not candles:
                    time.sleep(2.0)
                    continue

                # The endpoint only publishes closed 1m intervals; candles[-1] is the most recently completed minute bar
                closed_bar = candles[-1]
                bar_time_str = closed_bar[0]

                if bar_time_str == self.last_evaluated_bar:
                    time.sleep(1.0)
                    continue

                self.last_evaluated_bar = bar_time_str
                bar_dt = datetime.fromisoformat(bar_time_str)
                bar_close_cutoff_epoch = bar_dt.timestamp() + 60.0
                btime = bar_dt.time()
                o, h, l, c = float(closed_bar[1]), float(closed_bar[2]), float(closed_bar[3]), float(closed_bar[4])

                # Opening Shock Stand-Aside: 09:15 - 09:45
                if btime < dtime(9, 45, 0):
                    self.or_high = max(self.or_high, h)
                    self.or_low = min(self.or_low, l)
                    print(f"⏳ [OPENING SHOCK] [{btime.strftime('%H:%M:%S')}] Bar Close: {c:.2f} | OR High: {self.or_high:.2f} | OR Low: {self.or_low:.2f}")
                    time.sleep(3.0)
                    continue

                if self.shock_active:
                    print(f"🔓 [OPENING SHOCK CLEARED] OR High: {self.or_high:.2f} | OR Low: {self.or_low:.2f} | Width: {self.or_high - self.or_low:.2f} pts")
                    self.shock_active = False

                # Friction & Slippage calculation conditioned on Expiry Calendar
                premium_est = max(20.0, c * 0.005)
                # On 0-DTE expiry days, gamma is ~3x higher near ATM (0.0035 vs 0.0012)
                effective_gamma = 0.0035 if self.is_expiry_day else 0.0012
                now_t = datetime.combine(datetime.today(), btime)
                market_close_t = datetime.combine(datetime.today(), dtime(15, 30, 0))
                mins_to_close = max(0.0, (market_close_t - now_t).total_seconds() / 60.0)

                fric = self.slippage.compute_drag(
                    premium=premium_est,
                    bid=premium_est * 0.985,
                    ask=premium_est * 1.015,
                    minutes_to_close=mins_to_close,
                    gamma=effective_gamma
                )
                spread_ratio = fric.bid_ask_spread / premium_est

                # Calculate session KER & EWMA-KER smoothing (alpha=0.15)
                disp = abs(c - float(candles[0][1]))
                tot_p = max(0.1, sum(abs(float(candles[k][4]) - float(candles[k-1][4])) for k in range(1, len(candles))))
                raw_ker = disp / tot_p
                self.session_ker = raw_ker
                self.ewma_ker = 0.15 * raw_ker + 0.85 * self.ewma_ker

                # 1m Realized ATR calculation across last 14 bars
                lookback_bars = candles[-14:] if len(candles) >= 14 else candles
                atr_1m = sum(max(float(b[2]) - float(b[3]), 0.1) for b in lookback_bars) / max(1, len(lookback_bars))

                # 1. Evaluate Active In-Flight Position Lifecycle
                if self.apm.state in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK}:
                    # Read current live option LTP if contract token/strike is known
                    cur_opt_quote = None
                    if self.apm.payload and self.apm.payload.strike_contract:
                        try:
                            # Parse strike from payload contract name e.g. "NIFTY 22250 PE [ITM]"
                            parts = self.apm.payload.strike_contract.split()
                            pos_strike = int(parts[1])
                            pos_type = parts[2]
                            cur_opt_quote = self.resolve_real_option_quote(pos_strike, pos_type)
                        except Exception:
                            pass

                    cur_opt_ltp = cur_opt_quote.get("ltp") if cur_opt_quote else None

                    apm_state, trade_summary = self.apm.evaluate_bar(
                        bar_open=o,
                        bar_high=h,
                        bar_low=l,
                        bar_close=c,
                        bar_time_str=bar_time_str,
                        current_opt_ltp=cur_opt_ltp,
                        atr_1m=atr_1m
                    )
                    if apm_state == STATE_LIQUIDATED:
                        pnl = trade_summary.get("pnl_pts", 0.0)
                        opt_pnl = trade_summary.get("opt_pnl_pts")
                        pnl_emoji = "🟢" if pnl > 0 else "🔴"
                        opt_pnl_str = f" | Option PnL: {opt_pnl:+.2f} pts" if opt_pnl is not None else ""
                        self.last_exit_price = trade_summary.get("exit_price")
                        self.last_exit_direction = trade_summary.get("direction")
                        print(f"🔔 [POSITION EXITED] Reason: {trade_summary.get('exit_reason')} | Exit Spot: {trade_summary.get('exit_price'):.1f} | Spot PnL: {pnl_emoji} {pnl:+.1f} pts{opt_pnl_str}")
                    elif self.apm.payload:
                        p = self.apm.payload
                        trailed_tag = ""
                        if p.half_booked:
                            trailed_tag = f" [RUNNER 50% TRAIL | Opt HWM: ₹{p.opt_peak_hwm:.2f} | Opt Trail SL: ₹{p.runner_trailing_sl:.2f}]"
                        elif p.trail_locked:
                            trailed_tag = " [TRAIL LOCKED +4]"
                        opt_live_str = f" | Option LTP: ₹{p.opt_current_ltp:.2f} (Entry: ₹{p.opt_entry_ltp:.2f})" if p.opt_entry_ltp else ""
                        print(f"🛡️ [IN-FLIGHT POSITION] {p.strike_contract} | Entry Spot: {p.entry_price:.1f} | Current SL: {p.current_sl:.1f}{trailed_tag}{opt_live_str}")

                # 2. Causal Setup Detection (Only if FLAT / STANDBY / LIQUIDATED)
                total_range = max(0.1, h - l)
                upper_wick = h - max(o, c)
                lower_wick = min(o, c) - l

                # 1-Strike In-The-Money (ITM) Strike Contract Resolver (K ± 50, Delta ≈ 0.65)
                # Bridges 81% ATM liquidity with theta immunity and +10 pt option gain delivery
                atm_strike = int(round(c / 50.0) * 50)
                ce_itm_strike = atm_strike - 50  # 1-strike ITM for Call
                pe_itm_strike = atm_strike + 50  # 1-strike ITM for Put
                ce_contract = f"NIFTY {ce_itm_strike} CE [ITM]"
                pe_contract = f"NIFTY {pe_itm_strike} PE [ITM]"

                signal_display = "WAIT"
                # Target: +15 spot pts yields +10.0 option strike pts on 0.65 delta
                target_pts = 15.0
                # Volatility-Scaled Stop Loss: max(12.0, 1.2 * ATR_1m) removes noise whipsaw
                sl_pts = round(max(12.0, 1.2 * atr_1m), 1)

                entry_dir = None
                contract_choice = None
                chosen_strike = None

                # Dynamic Session Phase Variance Decay (SPVD) Energy Gate Check
                can_enter_energy, e_atr_rem, req_energy = self.apm.check_session_energy_gate(
                    current_time=btime,
                    daily_norm_atr=120.0,
                    target_pts=target_pts,
                    buffer_multiplier=1.5,
                    session_ker=self.ewma_ker
                )

                if c > self.or_high:
                    entry_dir = "CE"
                    contract_choice = ce_contract
                    chosen_strike = ce_itm_strike
                    signal_display = f"🎯 [BUY {ce_contract}] @ Breakout > {self.or_high:.1f} | Target: +{target_pts}pts | Vol-SL: -{sl_pts}pts (ATR:{atr_1m:.1f})"
                elif c < self.or_low:
                    entry_dir = "PE"
                    contract_choice = pe_contract
                    chosen_strike = pe_itm_strike
                    signal_display = f"🎯 [BUY {pe_contract}] @ Breakdown < {self.or_low:.1f} | Target: +{target_pts}pts | Vol-SL: -{sl_pts}pts (ATR:{atr_1m:.1f})"
                elif lower_wick >= 6.0 and (lower_wick / total_range) >= 0.40:
                    entry_dir = "CE"
                    contract_choice = ce_contract
                    chosen_strike = ce_itm_strike
                    signal_display = f"🎯 [BUY {ce_contract}] @ Bullish Wick Rejection | Target: +{target_pts}pts | Vol-SL: -{sl_pts}pts"
                elif upper_wick >= 6.0 and (upper_wick / total_range) >= 0.40:
                    entry_dir = "PE"
                    contract_choice = pe_contract
                    chosen_strike = pe_itm_strike
                    signal_display = f"🎯 [BUY {pe_contract}] @ Bearish Wick Rejection | Target: +{target_pts}pts | Vol-SL: -{sl_pts}pts"

                # Calculate cumulative session high and low to detect Macro Trend Exhaustion
                session_high = max(float(b[2]) for b in candles)
                session_low = min(float(b[3]) for b in candles)
                session_range = session_high - session_low
                # Macro ATR Extension Cap: If session has already moved > 2.5x 20d ATR (300 pts),
                # new trend breakout entries pay peak IV and risk mean-reversion whipsaw.
                atr_extension_exhausted = (session_range > 2.5 * 120.0)

                # Re-Entry Displacement Gate: Enforce that re-entering in the same direction
                # requires price to displace at least 1.0 * ATR_1m past the previous exit price.
                # Prevents taking back-to-back losing micro-scalps into the same stall zone.
                insufficient_displacement = False
                if self.last_exit_price is not None and self.last_exit_direction == entry_dir:
                    min_disp_pts = max(8.0, 1.0 * atr_1m)
                    if entry_dir == "PE" and (self.last_exit_price - c) < min_disp_pts:
                        insufficient_displacement = True
                    elif entry_dir == "CE" and (c - self.last_exit_price) < min_disp_pts:
                        insufficient_displacement = True

                # Dynamic Regime Classification: Gear 1 (Range Scalper) vs Gear 2 (Trend Expansion)
                current_gear = "GEAR_2_TREND" if (self.ewma_ker >= 0.35 and (self.or_high - self.or_low) >= 70.0) else "GEAR_1_RANGE"

                # Gear 1 Range Day: Enforce Lunch Dead-Zone Freeze (11:00 AM - 13:30 PM)
                in_lunch_dead_zone = (current_gear == "GEAR_1_RANGE" and dtime(11, 0) <= btime <= dtime(13, 30))

                # Gear Invariants:
                # On Gear 2 Trend days: strictly FORBID wick-reversion fading against the macro drift
                is_counter_trend_fade = False
                if current_gear == "GEAR_2_TREND":
                    if c < self.or_low and entry_dir == "CE":
                        is_counter_trend_fade = True
                    elif c > self.or_high and entry_dir == "PE":
                        is_counter_trend_fade = True

                # Evaluate ordered gate vetoes, candidate observation, and paper APM entry via production helper
                gate_res = self.evaluate_entry_gates(
                    entry_dir=entry_dir,
                    signal_display=signal_display,
                    in_lunch_dead_zone=in_lunch_dead_zone,
                    is_counter_trend_fade=is_counter_trend_fade,
                    can_enter_energy=can_enter_energy,
                    e_atr_rem=e_atr_rem,
                    req_energy=req_energy,
                    insufficient_displacement=insufficient_displacement,
                    atr_1m=atr_1m,
                    atr_extension_exhausted=atr_extension_exhausted,
                    session_range=session_range,
                    spread_ratio=spread_ratio,
                    chosen_strike=chosen_strike,
                    contract_choice=contract_choice,
                    bar_close_cutoff_epoch=bar_close_cutoff_epoch,
                    spot_close=c,
                    bar_time_str=bar_time_str,
                    sl_pts=sl_pts,
                    target_pts=target_pts,
                    total_drag_pts=fric.total_drag_pts,
                    current_gear=current_gear,
                    btime=btime
                )
                signal_display = gate_res["signal_display"]
                risk_flag = gate_res["risk_flag"]
                candidate_status = gate_res["candidate_status"]
                candidate_reason = gate_res["candidate_reason"]
                option_candidate = gate_res["option_candidate"]

                # Emit Append-Only JSONL Audit Row with provenance and explicit replay labeling
                audit_row = {
                    "timestamp": bar_time_str,
                    "run_id": getattr(self, "run_id", "UNKNOWN"),
                    "pid": getattr(self, "pid", None),
                    "git_sha": getattr(self, "git_sha", "UNKNOWN"),
                    "execution_mode": "CAPTURE_RECEIVE_TIME_REPLAY_ONLY",
                    "receive_time_verified": True,
                    "exchange_event_time_verified": False,
                    "spot_nifty": c,
                    "high": h,
                    "low": l,
                    "atr_1m": round(atr_1m, 2),
                    "raw_ker": round(raw_ker, 4),
                    "ewma_ker": round(self.ewma_ker, 4),
                    "drag_pts": round(fric.total_drag_pts, 2),
                    "spread_ratio": round(spread_ratio, 4),
                    "advisory": signal_display,
                    "risk_flag": risk_flag,
                    "apm_state": self.apm.state,
                    "candidate_status": candidate_status,
                }
                if candidate_reason:
                    audit_row["candidate_reason"] = candidate_reason
                if option_candidate:
                    audit_row["option_candidate"] = option_candidate
                self.emit_and_append_audit_log(audit_row)

                print(f"📊 [{btime.strftime('%H:%M:%S')}] Spot: {c:.2f} (H:{h:.2f} L:{l:.2f}) | ATR: {atr_1m:.1f} | Drag: {fric.total_drag_pts:.2f}pts | EWMA-KER: {self.ewma_ker:.3f}")
                if "BUY" in signal_display:
                    print(f"   {signal_display}")
                else:
                    print(f"   Status: SCALP_MONITORING | Setup: WAIT")

                # If post-market, trigger Parquet audit compression
                if btime >= dtime(15, 30, 0):
                    self.compress_audit_log_to_parquet()

                time.sleep(3.0)

            except Exception as e:
                print(f"Polling loop exception: {e}")
                time.sleep(3.0)

if __name__ == "__main__":
    advisor = SentinelLiveFeedAdvisor()
    advisor.run_loop()
