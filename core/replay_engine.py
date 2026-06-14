from __future__ import annotations
from core.paths import logs_dir, data_root, runtime_dir
from core.learning_paths import canonical_rejected_candidates_path, canonical_suggestions_log_path

import csv
import json
import hashlib
import random
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from config import config as cfg
from core.indicators_live import compute_indicators
from core.option_chain import fetch_option_chain
from core.ohlc_buffer import OhlcBuffer
from core.regime_prob_model import RegimeProbModel
from core.strategy_gatekeeper import StrategyGatekeeper
from core.trade_scoring import compute_trade_score
from core.risk_engine import RiskEngine
from core.execution_guard import ExecutionGuard
from strategies.trade_builder import TradeBuilder
from core.slippage_model import estimate_slippage


def _load_instruments_map(path: Path) -> Dict[int, dict]:
    if not path.exists():
        return {}
    out = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                token = int(row.get("instrument_token"))
            except Exception:
                continue
            out[token] = row
    return out


def _symbol_from_token(token: int, symbol_set: set, inst_map: Dict[int, dict]) -> Optional[str]:
    row = inst_map.get(token)
    if not row:
        return None
    name = (row.get("name") or "").upper()
    ts = (row.get("tradingsymbol") or "").upper()
    for sym in symbol_set:
        if name == sym:
            return sym
        if ts.startswith(sym):
            return sym
    return None


def _date_bounds(date_str: str) -> Tuple[float, float]:
    # Use Asia/Kolkata for trading-day boundaries
    try:
        tz = timezone(timedelta(hours=5, minutes=30))
        day = datetime.fromisoformat(date_str).date()
        start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz)
        end = start + timedelta(days=1)
        return start.timestamp(), end.timestamp()
    except Exception:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        return now.timestamp(), (now + timedelta(days=1)).timestamp()


def _coerce_epoch(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
        if numeric > 1_000_000_000_000:
            return numeric / 1000.0
        return numeric
    except Exception:
        pass
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _record_epoch(record: dict, default: Optional[float] = None) -> Optional[float]:
    if not isinstance(record, dict):
        return default
    for key in (
        "ts_epoch",
        "timestamp_epoch",
        "timestamp_epoch_ms",
        "quote_ts_epoch",
        "generated_at",
        "timestamp",
        "ts_iso",
        "last_seen_ts",
        "trade_lifecycle_ts",
    ):
        epoch = _coerce_epoch(record.get(key))
        if epoch is not None:
            return epoch
    return default


def _match_symbol(record: dict, symbol: Optional[str]) -> bool:
    if not symbol:
        return True
    if not isinstance(record, dict):
        return False
    symbol_text = str(symbol or "").strip().upper()
    direct = str(record.get("symbol") or record.get("underlying") or "").strip().upper()
    if direct and direct == symbol_text:
        return True
    tradingsymbol = str(record.get("tradingsymbol") or record.get("instrument_id") or "").strip().upper()
    if tradingsymbol and tradingsymbol.startswith(symbol_text):
        return True
    return False


def _within_window(epoch: Optional[float], start_epoch: Optional[float], end_epoch: Optional[float]) -> bool:
    if epoch is None:
        return start_epoch is None and end_epoch is None
    if start_epoch is not None and epoch < start_epoch:
        return False
    if end_epoch is not None and epoch > end_epoch:
        return False
    return True


def _json_file(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _jsonl_file(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = str(raw_line or "").strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def _stable_sort_key(record: dict) -> tuple:
    epoch = _record_epoch(record)
    text = json.dumps(record, sort_keys=True, default=str, separators=(",", ":"))
    return (
        float(epoch) if epoch is not None else float("-inf"),
        str(record.get("trade_id") or record.get("advisory_id") or record.get("trace_id") or ""),
        str(record.get("stage") or record.get("status") or ""),
        text,
    )


def _artifact_paths(runtime_root_override: Optional[Path] = None) -> dict[str, Path]:
    base = Path(runtime_root_override).expanduser() if runtime_root_override else runtime_dir()
    logs_root = base / "logs"
    observability_root = base / "observability"
    return {
        "advisory_latest": base / "advisory_latest.json",
        "top_opportunities_latest": base / "top_opportunities_latest.json",
        "feed_runtime_latest": base / "feed_runtime_latest.json",
        "pipeline_funnel": observability_root / "pipeline_funnel.json",
        "trade_lifecycle": observability_root / "trade_lifecycle.jsonl",
        "suggestions": logs_root / canonical_suggestions_log_path().name,
        "review_queue": logs_root / "review_queue.json",
        "rejected_candidates": logs_root / canonical_rejected_candidates_path().name,
    }


def _project_row(
    row: dict,
    *,
    source: str,
    default_epoch: Optional[float] = None,
    symbol: Optional[str] = None,
    start_epoch: Optional[float] = None,
    end_epoch: Optional[float] = None,
) -> Optional[dict]:
    if not isinstance(row, dict):
        return None
    projected = dict(row)
    projected["replay_source"] = source
    epoch = _record_epoch(projected, default=default_epoch)
    if epoch is not None:
        projected["replay_ts_epoch"] = float(epoch)
    if not _match_symbol(projected, symbol):
        return None
    if not _within_window(epoch, start_epoch, end_epoch):
        return None
    return projected


class ReplayEngine:
    def __init__(self, db_path: Optional[Path] = None, seed: int = 1):
        self.db_path = Path(db_path) if db_path else Path(cfg.TRADE_DB_PATH)
        self.seed = int(seed)
        self.trade_builder = TradeBuilder()
        self.gatekeeper = StrategyGatekeeper()
        self.risk_engine = RiskEngine()
        self.exec_guard = ExecutionGuard()
        self.regime_model = RegimeProbModel(getattr(cfg, "REGIME_MODEL_PATH", "models/regime_model.json"))
        self.portfolio = {
            "capital": float(getattr(cfg, "CAPITAL", 100000)),
            "daily_loss": 0.0,
            "daily_profit": 0.0,
            "trades_today": 0,
            "equity_high": float(getattr(cfg, "CAPITAL", 100000)),
        }
        self.active_trades = []

    @staticmethod
    def replay_runtime_artifacts(
        *,
        symbol: str | None = None,
        start: str | float | int | None = None,
        end: str | float | int | None = None,
        runtime_root: Path | str | None = None,
    ) -> dict:
        start_epoch = _coerce_epoch(start)
        end_epoch = _coerce_epoch(end)
        if start_epoch is not None and end_epoch is not None and start_epoch > end_epoch:
            raise ValueError("replay_window_start_after_end")

        symbol_text = str(symbol or "").strip().upper() or None
        paths = _artifact_paths(Path(runtime_root).expanduser() if runtime_root else None)
        artifacts: dict[str, dict] = {}
        missing_artifacts: list[str] = []
        notes: list[str] = []

        def _register(name: str, path: Path, count: int = 0) -> None:
            present = path.exists()
            artifacts[name] = {
                "path": str(path),
                "present": bool(present),
                "row_count": int(count),
            }
            if not present:
                missing_artifacts.append(name)

        market_state_snapshots: list[dict] = []
        pipeline_funnel_records: list[dict] = []
        candidate_pool: list[dict] = []
        ranked_candidates: list[dict] = []
        advisory_outputs: list[dict] = []
        execution_path: list[dict] = []
        allocation_outcomes: list[dict] = []

        feed_path = paths["feed_runtime_latest"]
        feed_raw = _json_file(feed_path) if feed_path.exists() else None
        if isinstance(feed_raw, dict):
            default_epoch = _coerce_epoch(feed_raw.get("generated_at"))
            payload = feed_raw.get("payload", feed_raw)
            if isinstance(payload, dict):
                projected = _project_row(
                    payload,
                    source="feed_runtime_latest",
                    default_epoch=default_epoch,
                    start_epoch=start_epoch,
                    end_epoch=end_epoch,
                )
                if projected is not None:
                    market_state_snapshots.append(projected)
            else:
                notes.append("invalid_artifact:feed_runtime_latest")
        elif feed_path.exists():
            notes.append("invalid_artifact:feed_runtime_latest")
        _register("feed_runtime_latest", feed_path, len(market_state_snapshots))

        funnel_path = paths["pipeline_funnel"]
        funnel_raw = _json_file(funnel_path) if funnel_path.exists() else None
        if isinstance(funnel_raw, dict):
            projected = _project_row(
                funnel_raw,
                source="pipeline_funnel",
                start_epoch=start_epoch,
                end_epoch=end_epoch,
            )
            if projected is not None:
                pipeline_funnel_records.append(projected)
        elif funnel_path.exists():
            notes.append("invalid_artifact:pipeline_funnel")
        _register("pipeline_funnel", funnel_path, len(pipeline_funnel_records))

        lifecycle_path = paths["trade_lifecycle"]
        lifecycle_rows = []
        if lifecycle_path.exists():
            for row in _jsonl_file(lifecycle_path):
                projected = _project_row(
                    row,
                    source="trade_lifecycle",
                    symbol=symbol_text,
                    start_epoch=start_epoch,
                    end_epoch=end_epoch,
                )
                if projected is not None:
                    lifecycle_rows.append(projected)
        lifecycle_rows.sort(key=_stable_sort_key)
        for row in lifecycle_rows:
            stage = str(row.get("stage") or "").strip().lower()
            if stage == "candidate_generation":
                candidate_pool.append(row)
            elif stage in {"readiness_gating", "execution_feasibility", "emission_projection"}:
                execution_path.append(row)
        _register("trade_lifecycle", lifecycle_path, len(lifecycle_rows))

        top_path = paths["top_opportunities_latest"]
        top_raw = _json_file(top_path) if top_path.exists() else None
        if isinstance(top_raw, dict):
            payload = top_raw.get("payload", top_raw)
            default_epoch = _coerce_epoch(top_raw.get("generated_at"))
            if isinstance(payload, dict):
                for bucket_name, source_key in (
                    ("executable", "top_executable_opportunities"),
                    ("advisory", "top_advisory_opportunities"),
                ):
                    for row in list(payload.get(source_key) or []):
                        projected = _project_row(
                            row,
                            source=f"top_opportunities_latest:{bucket_name}",
                            default_epoch=default_epoch,
                            symbol=symbol_text,
                            start_epoch=start_epoch,
                            end_epoch=end_epoch,
                        )
                        if projected is None:
                            continue
                        projected.setdefault("opportunity_bucket", bucket_name)
                        ranked_candidates.append(projected)
            else:
                notes.append("invalid_artifact:top_opportunities_latest")
        elif top_path.exists():
            notes.append("invalid_artifact:top_opportunities_latest")
        ranked_candidates.sort(key=_stable_sort_key)
        _register("top_opportunities_latest", top_path, len(ranked_candidates))

        advisory_path = paths["advisory_latest"]
        advisory_raw = _json_file(advisory_path) if advisory_path.exists() else None
        if isinstance(advisory_raw, dict):
            payload = advisory_raw.get("payload", advisory_raw)
            default_epoch = _coerce_epoch(advisory_raw.get("generated_at"))
            rows = payload.get("rows") if isinstance(payload, dict) else None
            if isinstance(rows, list):
                for row in rows:
                    projected = _project_row(
                        row,
                        source="advisory_latest",
                        default_epoch=default_epoch,
                        symbol=symbol_text,
                        start_epoch=start_epoch,
                        end_epoch=end_epoch,
                    )
                    if projected is not None:
                        advisory_outputs.append(projected)
            else:
                notes.append("invalid_artifact:advisory_latest")
        elif advisory_path.exists():
            notes.append("invalid_artifact:advisory_latest")
        _register("advisory_latest", advisory_path, len(advisory_outputs))

        suggestions_path = paths["suggestions"]
        suggestion_rows = []
        if suggestions_path.exists():
            for row in _jsonl_file(suggestions_path):
                projected = _project_row(
                    row,
                    source="suggestions_log",
                    symbol=symbol_text,
                    start_epoch=start_epoch,
                    end_epoch=end_epoch,
                )
                if projected is not None:
                    suggestion_rows.append(projected)
        suggestion_rows.sort(key=_stable_sort_key)
        advisory_outputs.extend(suggestion_rows)
        _register("suggestions", suggestions_path, len(suggestion_rows))

        queue_path = paths["review_queue"]
        queue_rows = []
        if queue_path.exists():
            queue_raw = _json_file(queue_path)
            if isinstance(queue_raw, list):
                for row in queue_raw:
                    projected = _project_row(
                        row,
                        source="review_queue",
                        symbol=symbol_text,
                        start_epoch=start_epoch,
                        end_epoch=end_epoch,
                    )
                    if projected is not None:
                        queue_rows.append(projected)
            else:
                notes.append("invalid_artifact:review_queue")
        queue_rows.sort(key=_stable_sort_key)
        advisory_outputs.extend(queue_rows)
        _register("review_queue", queue_path, len(queue_rows))

        rejected_path = paths["rejected_candidates"]
        rejected_rows = []
        if rejected_path.exists():
            for row in _jsonl_file(rejected_path):
                projected = _project_row(
                    row,
                    source="rejected_candidates",
                    symbol=symbol_text,
                    start_epoch=start_epoch,
                    end_epoch=end_epoch,
                )
                if projected is None:
                    continue
                projected.setdefault("stage", "candidate_generation")
                rejected_rows.append(projected)
        rejected_rows.sort(key=_stable_sort_key)
        candidate_pool.extend(rejected_rows)
        _register("rejected_candidates", rejected_path, len(rejected_rows))

        if not ranked_candidates:
            for row in lifecycle_rows:
                if str(row.get("stage") or "").strip().lower() != "scoring_ranking":
                    continue
                fallback_ranked = dict(row)
                fallback_ranked.setdefault("opportunity_bucket", "unknown")
                ranked_candidates.append(fallback_ranked)
            ranked_candidates.sort(key=_stable_sort_key)

        advisory_outputs.sort(key=_stable_sort_key)
        candidate_pool.sort(key=_stable_sort_key)
        execution_path.sort(key=_stable_sort_key)

        allocation_seen: set[str] = set()
        for row in ranked_candidates + advisory_outputs:
            if not any(
                row.get(field) not in (None, "", [])
                for field in ("slot_id", "allocation_reason", "allocation_score", "capital_assigned", "size_multiplier_effective")
            ):
                continue
            key = json.dumps(
                {
                    "trade_id": row.get("trade_id"),
                    "source": row.get("replay_source"),
                    "allocation_reason": row.get("allocation_reason"),
                    "slot_id": row.get("slot_id"),
                },
                sort_keys=True,
                default=str,
            )
            if key in allocation_seen:
                continue
            allocation_seen.add(key)
            allocation_outcomes.append(row)
        allocation_outcomes.sort(key=_stable_sort_key)

        if not candidate_pool:
            notes.append("candidate_pool_unavailable")
        if not ranked_candidates:
            notes.append("ranked_candidates_unavailable")
        if not advisory_outputs:
            notes.append("advisory_outputs_unavailable")

        return {
            "schema_version": 1,
            "mode": "runtime_artifact_replay",
            "symbol": symbol_text,
            "window": {
                "start": start,
                "end": end,
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
            },
            "runtime_root": str(Path(runtime_root).expanduser() if runtime_root else runtime_dir()),
            "artifacts": artifacts,
            "missing_artifacts": missing_artifacts,
            "pipeline_funnel": pipeline_funnel_records,
            "market_state_snapshots": market_state_snapshots,
            "candidate_pool": candidate_pool,
            "ranked_candidates": ranked_candidates,
            "advisory_outputs": advisory_outputs,
            "allocation_outcomes": allocation_outcomes,
            "execution_path": execution_path,
            "summary": {
                "market_state_count": len(market_state_snapshots),
                "candidate_count": len(candidate_pool),
                "ranked_count": len(ranked_candidates),
                "advisory_count": len(advisory_outputs),
                "allocation_count": len(allocation_outcomes),
                "execution_path_count": len(execution_path),
            },
            "notes": notes,
        }

    def _load_ticks(self, start_epoch: float, end_epoch: float) -> List[Tuple[float, int, float, int]]:
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT timestamp_epoch, instrument_token, last_price, volume FROM ticks "
            "WHERE timestamp_epoch >= ? AND timestamp_epoch < ? ORDER BY timestamp_epoch ASC, instrument_token ASC, rowid ASC",
            (start_epoch, end_epoch),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def _load_depth(self, start_epoch: float, end_epoch: float) -> List[Tuple[float, int, str]]:
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT timestamp_epoch, instrument_token, depth_json FROM depth_snapshots "
            "WHERE timestamp_epoch >= ? AND timestamp_epoch < ? ORDER BY timestamp_epoch ASC, instrument_token ASC, rowid ASC",
            (start_epoch, end_epoch),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def _normalize_option_chain_for_replay(self, chain: List[dict], ts_epoch: float, replay_day: str) -> List[dict]:
        normalized: List[dict] = []
        for opt in list(chain or []):
            row = dict(opt or {})
            row["quote_ts_epoch"] = float(ts_epoch)
            row["quote_age_sec"] = 0.0
            row["timestamp"] = float(ts_epoch)
            row["expiry"] = str(row.get("expiry") or replay_day)
            row["expiry_date"] = str(row.get("expiry_date") or row["expiry"])
            normalized.append(row)
        return normalized

    def _normalize_trade_payload(self, trade, *, ts_epoch: float, trace_id: str) -> dict:
        payload = asdict(trade)
        stable_trade_id = hashlib.sha256(
            f"{self.seed}|{trace_id}|{payload.get('symbol')}|{payload.get('strike')}|{payload.get('option_type')}".encode(
                "utf-8"
            )
        ).hexdigest()[:20]
        stable_iso = datetime.fromtimestamp(float(ts_epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        payload["trade_id"] = f"replay-{stable_trade_id}"
        payload["timestamp"] = stable_iso
        for key in ("first_seen", "last_seen", "activated_ts"):
            if key in payload and payload.get(key) is not None:
                payload[key] = stable_iso
        return payload

    def replay_day(self, date_str: str, symbols: List[str], speed: float = 1.0) -> Path:
        symbol_set = {s.upper() for s in symbols}
        inst_map = _load_instruments_map(data_root() / "kite_instruments.csv")
        start_epoch, end_epoch = _date_bounds(date_str)
        ticks = self._load_ticks(start_epoch, end_epoch)
        depth = self._load_depth(start_epoch, end_epoch)
        local_ohlc_buffer = OhlcBuffer()

        # index depth by time
        depth_idx = 0
        latest_depth = {}
        out_path = logs_dir() / f"decisions_replay_{date_str}.json"
        out_path.parent.mkdir(exist_ok=True)

        trace_counter = 0
        local_rng = random.Random(self.seed)
        py_random_state = random.getstate()
        np_random_state = None
        np_random_module = None
        try:
            try:
                import numpy as _np  # type: ignore

                np_random_module = _np
                np_random_state = _np.random.get_state()
                _np.random.seed(self.seed)
            except Exception:
                np_random_state = None
                np_random_module = None
            random.seed(self.seed)
            with out_path.open("w") as f:
                for ts_epoch, token, price, volume in ticks:
                    # update depth snapshots up to this time
                    while depth_idx < len(depth) and depth[depth_idx][0] <= ts_epoch:
                        d_ts, d_token, d_json = depth[depth_idx]
                        latest_depth[d_token] = (d_ts, d_json)
                        depth_idx += 1
                    sym = _symbol_from_token(int(token), symbol_set, inst_map)
                    if not sym:
                        continue
                    if price is None:
                        continue
                        
                    for t_idx in range(len(self.active_trades) - 1, -1, -1):
                        active = self.active_trades[t_idx]
                        if not _match_symbol(active, sym):
                            continue
                        
                        outcome = None
                        exit_price = price
                        
                        if active["side"] == "BUY":
                            if price >= active["target"]:
                                outcome = "TARGET"
                            elif price <= active["stop_loss"]:
                                outcome = "STOP"
                        else:
                            if price <= active["target"]:
                                outcome = "TARGET"
                            elif price >= active["stop_loss"]:
                                outcome = "STOP"
                                
                        if outcome:
                            est = estimate_slippage(
                                side="SELL" if active["side"] == "BUY" else "BUY",
                                bid=price,
                                ask=price,
                                execution_entry=price,
                                qty=active["qty"],
                                volume=volume,
                                vol_z=0.0
                            )
                            exit_fill = est.executable_price_estimate or price
                            pl = (exit_fill - active["entry_fill"]) * active["qty"] if active["side"] == "BUY" else (active["entry_fill"] - exit_fill) * active["qty"]
                            
                            self.portfolio["capital"] += pl
                            self.portfolio["trades_today"] += 1
                            if pl < 0:
                                self.portfolio["daily_loss"] += abs(pl)
                            else:
                                self.portfolio["daily_profit"] += pl
                            
                            out_outcomes = logs_dir() / "candidate_outcomes.jsonl"
                            with out_outcomes.open("a") as out_f:
                                out_f.write(json.dumps({
                                    "trade_id": active["trade_id"],
                                    "symbol": active["symbol"],
                                    "outcome": outcome,
                                    "pl": pl,
                                    "exit_fill": exit_fill,
                                    "ts_epoch": ts_epoch
                                }) + "\n")
                                
                            self.active_trades.pop(t_idx)

                    local_ohlc_buffer.update_tick(sym, price, volume or 0, ts=ts_epoch)
                    bars = local_ohlc_buffer.get_bars(sym)
                    indicators_ok = len(bars) >= getattr(cfg, "OHLC_MIN_BARS", 30)
                    ind = compute_indicators(
                        bars,
                        vwap_window=getattr(cfg, "VWAP_WINDOW", 20),
                        atr_period=getattr(cfg, "ATR_PERIOD", 14),
                        adx_period=getattr(cfg, "ADX_PERIOD", 14),
                        vol_window=getattr(cfg, "VOL_WINDOW", 30),
                        slope_window=getattr(cfg, "VWAP_SLOPE_WINDOW", 10),
                    ) if bars else {}

                    vwap = ind.get("vwap") or price
                    atr = ind.get("atr") or max(1.0, price * 0.002)
                    adx = ind.get("adx") or 0.0
                    vol_z = ind.get("vol_z") or 0.0
                    vwap_slope = ind.get("vwap_slope") or 0.0

                    depth_imb = None
                    if token in latest_depth:
                        try:
                            depth_obj = json.loads(latest_depth[token][1])
                            depth_imb = depth_obj.get("imbalance")
                        except Exception:
                            depth_imb = None

                    features = {
                        "adx": adx,
                        "vwap_slope": vwap_slope,
                        "vol_z": vol_z,
                        "atr_pct": (atr / price) if price else 0.0,
                        "iv_mean": 0.0,
                        "ltp_acceleration": 0.0,
                        "option_chain_skew": 0.0,
                        "oi_delta": 0.0,
                        "depth_imbalance": depth_imb or 0.0,
                        "regime_transition_rate": 0.0,
                        "shock_score": 0.0,
                        "uncertainty_index": 0.0,
                        "macro_direction_bias": 0.0,
                        "x_regime_align": 0.0,
                        "x_vol_spillover": 0.0,
                        "x_lead_lag": 0.0,
                    }
                    regime_out = self.regime_model.predict(features)

                    market_data = {
                        "symbol": sym,
                        "ltp": price,
                        "vwap": vwap,
                        "atr": atr,
                        "vwap_slope": vwap_slope,
                        "vol_z": vol_z,
                        "adx_14": adx,
                        "depth_imbalance": depth_imb,
                        "indicators_ok": indicators_ok,
                        "indicators_age_sec": 0.0,
                        "regime_probs": regime_out.get("regime_probs"),
                        "primary_regime": regime_out.get("primary_regime"),
                        "regime_entropy": regime_out.get("regime_entropy"),
                        "unstable_regime_flag": regime_out.get("unstable_regime_flag"),
                        "shock_score": 0.0,
                        "uncertainty_index": 0.0,
                        "cross_asset_quality": {"stale_feeds": [], "missing": {}},
                        "execution_mode": "SIM",
                        "market_context": {
                            "execution_mode": "SIM",
                            "market_open": False,
                        },
                    }

                    # option chain (synthetic for deterministic replay)
                    try:
                        chain = fetch_option_chain(sym, price, force_synthetic=True)
                    except Exception:
                        chain = []
                    market_data["option_chain"] = self._normalize_option_chain_for_replay(
                        chain,
                        ts_epoch=float(ts_epoch),
                        replay_day=date_str,
                    )

                    trace_entropy = local_rng.getrandbits(64)
                    trace_hash = hashlib.sha256(
                        f"{self.seed}|{date_str}|{sym}|{trace_counter}|{float(ts_epoch):.6f}|{trace_entropy}".encode(
                            "utf-8"
                        )
                    ).hexdigest()[:16]
                    trace_id = f"replay-{date_str}-{sym}-{trace_hash}"

                    gate = self.gatekeeper.evaluate(market_data, mode="MAIN")
                    decision = {
                        "trace_id": trace_id,
                        "ts_epoch": ts_epoch,
                        "ts_iso": datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                        "symbol": sym,
                        "ltp": price,
                        "features": features,
                        "regime": regime_out.get("primary_regime"),
                        "regime_probs": regime_out.get("regime_probs"),
                        "regime_entropy": regime_out.get("regime_entropy"),
                        "unstable_regime_flag": regime_out.get("unstable_regime_flag"),
                        "gatekeeper_allowed": gate.allowed,
                        "gatekeeper_reasons": gate.reasons,
                        "risk_allowed": None,
                        "exec_guard_allowed": None,
                        "trade": None,
                        "why": {},
                    }

                    if gate.allowed:
                        trade = self.trade_builder.build(
                            market_data,
                            quick_mode=False,
                            debug_reasons=False,
                            force_family=gate.family,
                            allow_fallbacks=False,
                            allow_baseline=False,
                        )
                        if trade:
                            decision["trade"] = self._normalize_trade_payload(
                                trade,
                                ts_epoch=float(ts_epoch),
                                trace_id=trace_id,
                            )
                            allowed, reason = self.risk_engine.allow_trade(self.portfolio)
                            decision["risk_allowed"] = bool(allowed)
                            decision["risk_reason"] = reason
                            if allowed:
                                ok, guard_reason = self.exec_guard.validate(trade, self.portfolio, trade.regime)
                                decision["exec_guard_allowed"] = bool(ok)
                                decision["exec_guard_reason"] = guard_reason
                                
                                if ok:
                                    est = estimate_slippage(
                                        side=trade.side,
                                        bid=price,
                                        ask=price,
                                        execution_entry=trade.entry_price,
                                        qty=trade.qty,
                                        volume=volume,
                                        vol_z=vol_z
                                    )
                                    entry_fill = est.executable_price_estimate or trade.entry_price
                                    self.active_trades.append({
                                        "trade_id": trace_id,
                                        "symbol": sym,
                                        "side": trade.side,
                                        "qty": trade.qty,
                                        "target": trade.target,
                                        "stop_loss": trade.stop_loss,
                                        "entry_fill": entry_fill,
                                    })
                            # compute score explanation
                            try:
                                opt = market_data.get("option_chain", [{}])[0] if market_data.get("option_chain") else {}
                                rr = None
                                try:
                                    rr = abs(trade.target - trade.entry_price) / max(
                                        abs(trade.entry_price - trade.stop_loss), 1e-6
                                    )
                                except Exception:
                                    rr = None
                                detail = compute_trade_score(
                                    market_data,
                                    opt,
                                    trade.side,
                                    rr,
                                    getattr(trade, "strategy", None),
                                )
                                decision["why"] = {"score": detail.get("score"), "detail": detail}
                            except Exception:
                                decision["why"] = {}

                    f.write(json.dumps(decision, default=str) + "\n")
                    trace_counter += 1
                    if speed > 0:
                        time.sleep(1.0 / speed)
        finally:
            random.setstate(py_random_state)
            if np_random_module is not None and np_random_state is not None:
                np_random_module.random.set_state(np_random_state)
        return out_path
