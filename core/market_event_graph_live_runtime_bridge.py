"""Opt-in runtime bridge for real market-event graph live-source evidence.

The bridge is advisory only. It observes already-completed OHLC bars and writes
validated evidence rows only when universe, subscription, interval, and live
provenance truth are all explicit. Evidence rejection never changes feed,
strategy, risk, or execution output.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from config import config as cfg
from core.market_data import get_token_for_symbol
from core.market_event_graph_live_ohlc_buffer import shadow_ohlc_buffer
from core.market_event_graph_live_source import (
    LiveCapturedMetadataExporter,
    build_live_captured_metadata_row,
    default_live_capture_path,
)
from core.time_utils import IST_TZ

logger = logging.getLogger(__name__)

LIVE_UNIVERSE_NOT_CONFIGURED = "LIVE_UNIVERSE_NOT_CONFIGURED"
BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE = "BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE"
BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION = "BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION"
BROKER_TOKEN_DOMAIN_MISMATCH = "BROKER_TOKEN_DOMAIN_MISMATCH"
LIVE_BAR_PROVENANCE_UNPROVEN = "LIVE_BAR_PROVENANCE_UNPROVEN"
BAR_PROVIDER_MISMATCH = "BAR_PROVIDER_MISMATCH"
BAR_TOKEN_DOMAIN_MISMATCH = "BAR_TOKEN_DOMAIN_MISMATCH"
BAR_UNIVERSE_HASH_MISMATCH = "BAR_UNIVERSE_HASH_MISMATCH"
BAR_SYMBOL_MISMATCH = "BAR_SYMBOL_MISMATCH"
BAR_INSTRUMENT_TOKEN_MISMATCH = "BAR_INSTRUMENT_TOKEN_MISMATCH"
FEED_SESSION_ID_MISMATCH = "FEED_SESSION_ID_MISMATCH"
RECONNECT_GENERATION_MISMATCH = "RECONNECT_GENERATION_MISMATCH"
PRE_GENERATION_TICK_PROVENANCE = "PRE_GENERATION_TICK_PROVENANCE"
INDEX_INTERVAL_MISALIGNED = "INDEX_INTERVAL_MISALIGNED"
SNAPSHOT_INCOMPLETE = "SNAPSHOT_INCOMPLETE"


@dataclass(frozen=True)
class LiveUniverseContract:
    schema_version: int
    broker_provider: str
    token_domain: str
    name: str
    version: str
    effective_date: str
    source_retrieval_date: str
    source_page_updated_date: str
    official_source_url: str
    official_raw_sha256: str
    index_symbol: str
    index_instrument_token: int
    provider_native_index_identifier: str
    constituents: tuple[dict[str, Any], ...]
    broker_instrument_master: dict[str, Any]
    source_provenance: str
    capture_session_id: str | None
    canonical_sha256: str

    @property
    def constituent_symbols(self) -> tuple[str, ...]:
        return tuple(str(row["symbol"]).upper() for row in self.constituents)

    @property
    def constituent_tokens(self) -> tuple[int, ...]:
        return tuple(int(row["instrument_token"]) for row in self.constituents)


@dataclass
class LiveSourceBridgeResult:
    attempted: bool
    exported: bool
    reason: str
    latency_ms: dict[str, float] = field(default_factory=dict)
    accepted_constituent_count: int = 0
    rejected_identities: tuple[str, ...] = ()
    missing_constituents: tuple[str, ...] = ()
    audit: dict[str, Any] = field(default_factory=dict)


class LiveSourceRuntimeBridge:
    def __init__(
        self,
        *,
        exporter: LiveCapturedMetadataExporter | None = None,
        universe_contract: Mapping[str, Any] | None = None,
        subscription_evidence_provider: Callable[[LiveUniverseContract], Mapping[str, Any]] | None = None,
    ) -> None:
        self.exporter = exporter or LiveCapturedMetadataExporter(
            Path(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_PATH", default_live_capture_path()))
        )
        self._explicit_universe_contract = dict(universe_contract or {})
        self._subscription_evidence_provider = subscription_evidence_provider
        self._last_source_bar_end_epoch: float | None = None
        self._last_session_date: str | None = None
        self._write_failures = 0
        self._dropped_evidence_writes = 0
        self._rejection_write_failures = 0
        self._max_queue_depth = 0
        self._diagnostics: list[dict[str, Any]] = []
        self._rejection_path = Path(
            getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_REJECTION_PATH", "runtime/market_event_graph_live_shadow/rejections.jsonl")
        )

    def observe_cycle(
        self,
        snapshot_rows: Sequence[Mapping[str, Any]],
        *,
        cycle_cutoff: datetime,
    ) -> LiveSourceBridgeResult:
        latency_ms = {"snapshot_assembly": 0.0, "validation": 0.0, "queue_write": 0.0}
        if not bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)):
            return LiveSourceBridgeResult(False, False, "DISABLED", latency_ms=latency_ms)

        t0 = time.perf_counter()
        contract, reason = self._load_universe_contract()
        if contract is None:
            return self._reject(reason, latency_ms=latency_ms)

        subscription = self._subscription_evidence(contract)
        subscription_ok, subscription_reason, subscription_rejected = self._validate_subscription_evidence(contract, subscription)
        if not subscription_ok:
            return self._reject(subscription_reason, latency_ms=latency_ms, identities=subscription_rejected, audit=subscription)

        t1 = time.perf_counter()
        snapshot, snapshot_reason, rejected = self._assemble_snapshot(contract, subscription, cycle_cutoff=cycle_cutoff)
        latency_ms["snapshot_assembly"] = (time.perf_counter() - t1) * 1000.0
        if snapshot is None:
            return self._reject(snapshot_reason, latency_ms=latency_ms, identities=rejected, audit=subscription)

        validation_start = time.perf_counter()
        row = build_live_captured_metadata_row(
            session_date=str(snapshot["session_date"]),
            symbol=contract.index_symbol,
            interval_end=str(snapshot["interval_end"]),
            ts_epoch=float(snapshot["observed_at_epoch"]),
            source_bar_end_epoch=float(snapshot["source_bar_end_epoch"]),
            index_bar=snapshot["index_bar"],
            constituent_bars=snapshot["constituent_bars"],
            expected_constituents=len(contract.constituents),
            run_id=str(subscription.get("feed_session_id") or subscription["subscription_evidence_id"]),
            runtime_source_identifier=str(subscription["subscription_evidence_id"]),
            missing_constituents=[],
            stale_constituents=[],
            duplicate_constituents=[],
            misaligned_constituents=[],
            late_constituents=[],
            universe_name=contract.name,
            universe_version=contract.version,
            universe_hash=contract.canonical_sha256,
            expected_constituent_symbols=contract.constituent_symbols,
            index_instrument_token=contract.index_instrument_token,
            subscription_evidence_id=str(subscription["subscription_evidence_id"]),
        )
        row["observed_at_epoch"] = float(snapshot["observed_at_epoch"])
        row["index_source_bar_end_epoch"] = float(snapshot["index_source_bar_end_epoch"])
        row["subscription_evidence"] = dict(subscription)
        latency_ms["validation"] = (time.perf_counter() - validation_start) * 1000.0

        write_start = time.perf_counter()
        result = self.exporter.export_row(row)
        latency_ms["queue_write"] = (time.perf_counter() - write_start) * 1000.0
        latency_ms["total"] = (time.perf_counter() - t0) * 1000.0
        self._max_queue_depth = max(self._max_queue_depth, 1)
        if not result.written:
            self._write_failures += 1
            if result.reason == "WRITE_FAILED":
                self._dropped_evidence_writes += 1
            logger.warning("market_event_graph_live_source_write_failed reason=%s details=%s", result.reason, ",".join(result.details))
            return self._reject(result.reason, latency_ms=latency_ms, audit=subscription)

        self._last_source_bar_end_epoch = float(row["source_bar_end_epoch"])
        self._last_session_date = str(row["session_date"])
        return LiveSourceBridgeResult(
            attempted=True,
            exported=True,
            reason=result.reason,
            latency_ms=latency_ms,
            accepted_constituent_count=len(contract.constituents),
            audit=self._audit_payload(subscription),
        )

    def flush(self) -> dict[str, Any]:
        payload = self._audit_payload({})
        payload["flushed"] = True
        return payload

    def _load_universe_contract(self) -> tuple[LiveUniverseContract | None, str]:
        raw = dict(self._explicit_universe_contract or {})
        if not raw:
            path_text = str(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", "") or "").strip()
            if not path_text:
                return None, LIVE_UNIVERSE_NOT_CONFIGURED
            path = Path(path_text)
            if not path.exists():
                return None, BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None, BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE
        try:
            constituents = tuple(
                {"symbol": str(row["symbol"]).upper(), "instrument_token": int(row["instrument_token"])}
                for row in raw.get("constituents", [])
            )
            contract = LiveUniverseContract(
                schema_version=int(raw.get("schema_version") or 1),
                broker_provider=str(raw.get("broker_provider") or raw.get("token_domain") or "").lower().strip(),
                token_domain=str(raw.get("token_domain") or raw.get("broker_provider") or "").lower().strip(),
                name=str(raw["name"]),
                version=str(raw["version"]),
                effective_date=str(raw.get("effective_date") or ""),
                source_retrieval_date=str(raw.get("source_retrieval_date") or ""),
                source_page_updated_date=str(raw.get("source_page_updated_date") or ""),
                official_source_url=str(raw.get("official_source_url") or ""),
                official_raw_sha256=str(raw.get("official_raw_sha256") or ""),
                index_symbol=str(raw["index_symbol"]).upper(),
                index_instrument_token=int(raw["index_instrument_token"]),
                provider_native_index_identifier=str(raw.get("provider_native_index_identifier") or ""),
                constituents=constituents,
                broker_instrument_master=dict(raw.get("broker_instrument_master") or {}),
                source_provenance=str(
                    raw.get("source_provenance")
                    or raw.get("official_source_provenance")
                    or raw.get("official_source_url")
                    or ""
                ),
                capture_session_id=(str(raw["capture_session_id"]) if raw.get("capture_session_id") is not None else None),
                canonical_sha256=str(raw["canonical_sha256"]),
            )
        except Exception:
            return None, BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE
        provider = str(raw.get("broker_provider") or "").strip().lower()
        token_domain = str(raw.get("token_domain") or "").strip().lower()
        if provider and provider != "kite":
            return None, BROKER_TOKEN_DOMAIN_MISMATCH
        if token_domain and token_domain != "kite_instrument_token":
            return None, BROKER_TOKEN_DOMAIN_MISMATCH
        if provider != "kite" and raw.get("broker_provider") is not None:
            return None, BROKER_TOKEN_DOMAIN_MISMATCH
        if len(contract.constituents) < int(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_MIN_CONSTITUENTS", 40)):
            return None, BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE
        if len(set(contract.constituent_symbols)) != len(contract.constituent_symbols):
            return None, BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE
        if contract.canonical_sha256 != canonical_live_universe_sha256(contract):
            return None, BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE
        return contract, "OK"

    def _subscription_evidence(self, contract: LiveUniverseContract) -> dict[str, Any]:
        if self._subscription_evidence_provider is not None:
            return dict(self._subscription_evidence_provider(contract) or {})
        try:
            from core.kite_depth_ws import market_event_graph_subscription_evidence_for_tokens

            token_by_symbol = {
                contract.index_symbol: contract.index_instrument_token,
                **{str(row["symbol"]).upper(): int(row["instrument_token"]) for row in contract.constituents},
            }
            return dict(market_event_graph_subscription_evidence_for_tokens(token_by_symbol) or {})
        except Exception as exc:
            logger.warning("market_event_graph_subscription_evidence_provider_failed err=%s", type(exc).__name__)
            return {
                "subscription_evidence_id": "",
                "token_resolved_symbols": [],
                "subscription_requested_symbols": [],
                "subscription_request_succeeded_symbols": [],
                "mode_request_succeeded_symbols": [],
                "live_tick_observed_symbols": [],
                "full_payload_observed_symbols": [],
                "completed_bar_available_symbols": [],
                "token_by_symbol": {},
            }

    def _validate_subscription_evidence(
        self,
        contract: LiveUniverseContract,
        evidence: Mapping[str, Any],
    ) -> tuple[bool, str, tuple[str, ...]]:
        required = tuple([contract.index_symbol, *contract.constituent_symbols])
        required_set = set(required)
        rejected: list[str] = []
        if not str(evidence.get("subscription_evidence_id") or "").strip():
            return False, BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION, required
        if not str(evidence.get("feed_session_id") or "").strip():
            return False, BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION, required
        try:
            int(evidence.get("reconnect_generation"))
        except Exception:
            return False, BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION, required
        observed_tokens = {
            str(symbol).upper(): int(token)
            for symbol, token in (evidence.get("token_by_symbol") or {}).items()
            if token is not None
        }
        expected_tokens = {
            contract.index_symbol: contract.index_instrument_token,
            **{str(row["symbol"]).upper(): int(row["instrument_token"]) for row in contract.constituents},
        }
        if observed_tokens != expected_tokens:
            return False, BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION, tuple(required)
        token_lifecycle = evidence.get("token_lifecycle") or {}
        if not isinstance(token_lifecycle, Mapping):
            return False, BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION, tuple(required)
        evidence_session_id = str(evidence.get("feed_session_id") or "")
        evidence_generation = int(evidence.get("reconnect_generation"))
        for symbol in required:
            token = int(expected_tokens[symbol])
            row = token_lifecycle.get(str(token)) or token_lifecycle.get(token) or {}
            if not isinstance(row, Mapping):
                return False, BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION, (symbol,)
            if str(row.get("feed_session_id") or "") != evidence_session_id:
                return False, FEED_SESSION_ID_MISMATCH, (symbol,)
            try:
                row_generation = int(row.get("reconnect_generation"))
            except Exception:
                return False, RECONNECT_GENERATION_MISMATCH, (symbol,)
            if row_generation != evidence_generation:
                return False, RECONNECT_GENERATION_MISMATCH, (symbol,)
            subscribe_success = _coerce_float(row.get("subscribe_call_succeeded_epoch"))
            live_tick_first = _coerce_float(row.get("first_post_request_tick_epoch"))
            mode_success = _coerce_float(row.get("mode_request_succeeded_epoch"))
            full_first = _coerce_float(row.get("first_full_payload_epoch"))
            post_mode_full_first = _coerce_float(
                row.get("latest_post_mode_full_epoch")
                or row.get("latest_post_mode_full_receipt_epoch")
                or row.get("first_post_mode_full_epoch")
            )
            post_mode_full_count = _coerce_float(row.get("post_mode_full_count")) or 0.0
            latest_packet = row.get("latest_observation_packet") if isinstance(row.get("latest_observation_packet"), Mapping) else {}
            instrument_class = str((latest_packet or {}).get("instrument_class") or ("INDEX" if symbol == contract.index_symbol else "NSE_EQUITY")).upper()
            if subscribe_success is None:
                return False, "SUBSCRIPTION_REQUEST_FAILED", (symbol,)
            if live_tick_first is None or live_tick_first < subscribe_success:
                return False, "MISSING_POST_REQUEST_TICK", (symbol,)
            if mode_success is None:
                return False, "MODE_REQUEST_FAILED", (symbol,)
            if not bool(row.get("final_current_generation_local_mode_is_full")):
                return False, "MODE_COMMAND_SUPERSEDED_BY_SUBSCRIBE", (symbol,)
            # A reconnect can legitimately observe a full packet before the
            # latest mode request.  The canonical lifecycle fields prove the
            # stronger fact needed here: a full packet after that mode request.
            canonical_post_mode_full = (
                post_mode_full_count > 0
                and post_mode_full_first is not None
                and post_mode_full_first > mode_success
            )
            if canonical_post_mode_full:
                continue
            if full_first is None or full_first < mode_success:
                latest_callback = _coerce_float(row.get("latest_callback_receipt_epoch"))
                if latest_callback is None or latest_callback <= mode_success:
                    return False, "POST_MODE_CALLBACK_NOT_OBSERVED", (symbol,)
                structured_reason = str((latest_packet or {}).get("structured_reason") or "").strip()
                if instrument_class == "INDEX":
                    if structured_reason == "INDEX_PACKET_MODE_UNPROVEN":
                        return False, "INDEX_PACKET_MODE_UNPROVEN", (symbol,)
                    return False, "INDEX_FULL_PACKET_NOT_OBSERVED", (symbol,)
                return False, "EQUITY_FULL_DEPTH_NOT_OBSERVED", (symbol,)
        for field in (
            "token_resolved_symbols",
            "subscription_requested_symbols",
            "subscription_request_succeeded_symbols",
            "mode_request_succeeded_symbols",
            "live_tick_observed_symbols",
            "full_payload_observed_symbols",
        ):
            observed = tuple(str(symbol).upper() for symbol in evidence.get(field, []) or [])
            observed_set = set(observed)
            duplicate = sorted({symbol for symbol in observed if observed.count(symbol) > 1})
            extra = sorted(observed_set - required_set)
            missing = [symbol for symbol in required if symbol not in observed_set]
            if duplicate or extra or missing:
                rejected.extend(missing)
                rejected.extend(extra)
                rejected.extend(duplicate)
                return False, BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION, tuple(dict.fromkeys(rejected))
        return True, "OK", ()

    def _assemble_snapshot(
        self,
        contract: LiveUniverseContract,
        subscription: Mapping[str, Any],
        *,
        cycle_cutoff: datetime,
    ) -> tuple[dict[str, Any] | None, str, tuple[str, ...]]:
        index_bar = self._completed_bar_for(contract.index_symbol, cycle_cutoff=cycle_cutoff)
        if index_bar is None:
            return None, SNAPSHOT_INCOMPLETE, (contract.index_symbol,)
        index_end = _bar_end_epoch(index_bar)
        if index_end is None:
            return None, INDEX_INTERVAL_MISALIGNED, (contract.index_symbol,)
        ok, reason = _bar_has_live_provenance(
            index_bar,
            expected_symbol=contract.index_symbol,
            expected_token=contract.index_instrument_token,
            contract=contract,
            subscription=subscription,
        )
        if not ok:
            return None, reason, (contract.index_symbol,)

        constituent_bars: list[dict[str, Any]] = []
        for spec in contract.constituents:
            symbol = str(spec["symbol"]).upper()
            bar = self._completed_bar_for(symbol, cycle_cutoff=cycle_cutoff)
            if bar is None:
                return None, SNAPSHOT_INCOMPLETE, (symbol,)
            end_epoch = _bar_end_epoch(bar)
            if end_epoch != index_end:
                return None, INDEX_INTERVAL_MISALIGNED, (symbol,)
            ok, reason = _bar_has_live_provenance(
                bar,
                expected_symbol=symbol,
                expected_token=int(spec["instrument_token"]),
                contract=contract,
                subscription=subscription,
            )
            if not ok:
                return None, reason, (symbol,)
            bar = dict(bar)
            bar["symbol"] = symbol
            bar["instrument_token"] = int(spec["instrument_token"])
            bar["source_bar_end_epoch"] = float(index_end)
            bar["completed"] = True
            constituent_bars.append(bar)

        if self._last_source_bar_end_epoch is not None and float(index_end) <= float(self._last_source_bar_end_epoch):
            return None, "DUPLICATE_INTERVAL", ()
        if float(index_end) > float(cycle_cutoff.timestamp()):
            return None, "FUTURE_SOURCE_BAR", ()

        source_dt = datetime.fromtimestamp(float(index_end), tz=IST_TZ)
        return (
            {
                "session_date": source_dt.date().isoformat(),
                "interval_end": source_dt.isoformat(),
                "source_bar_end_epoch": float(index_end),
                "index_source_bar_end_epoch": float(index_end),
                "observed_at_epoch": float(cycle_cutoff.timestamp()),
                "index_bar": {**dict(index_bar), "source_bar_end_epoch": float(index_end), "instrument_token": contract.index_instrument_token, "completed": True},
                "constituent_bars": constituent_bars,
                "subscription": dict(subscription),
            },
            "OK",
            (),
        )

    def _completed_bar_for(self, symbol: str, *, cycle_cutoff: datetime) -> dict[str, Any] | None:
        bars = shadow_ohlc_buffer.get_completed_bars(symbol, as_of=cycle_cutoff)
        if not bars:
            return None
        latest = dict(bars[-1])
        if not isinstance(latest.get("ts"), datetime):
            return None
        return latest

    def _resolve_token(self, symbol: str) -> int | None:
        try:
            return get_token_for_symbol(symbol)
        except Exception:
            return None

    def _reject(
        self,
        reason: str,
        *,
        latency_ms: Mapping[str, float],
        identities: Sequence[str] = (),
        audit: Mapping[str, Any] | None = None,
    ) -> LiveSourceBridgeResult:
        row = {
            "reason": str(reason),
            "affected_identities": [str(item) for item in identities],
            "ts_epoch": time.time(),
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
        self._diagnostics.append(row)
        self._write_rejection(row, audit or {})
        logger.warning("market_event_graph_live_source_rejected reason=%s identities=%s", reason, ",".join(row["affected_identities"]))
        return LiveSourceBridgeResult(
            attempted=True,
            exported=False,
            reason=str(reason),
            latency_ms=dict(latency_ms),
            rejected_identities=tuple(row["affected_identities"]),
            missing_constituents=tuple(row["affected_identities"]),
            audit=self._audit_payload(audit or {}),
        )

    def _audit_payload(self, subscription: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "export_path": str(self.exporter.path),
            "last_source_bar_end_epoch": self._last_source_bar_end_epoch,
            "last_session_date": self._last_session_date,
            "write_failures": self._write_failures,
            "dropped_evidence_writes": self._dropped_evidence_writes,
            "rejection_write_failures": self._rejection_write_failures,
            "max_queue_high_water_mark": self._max_queue_depth,
            "diagnostic_count": len(self._diagnostics),
            "latest_diagnostic": dict(self._diagnostics[-1]) if self._diagnostics else None,
            "subscription_evidence": dict(subscription or {}),
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }

    def _write_rejection(self, row: Mapping[str, Any], audit: Mapping[str, Any]) -> None:
        try:
            self._rejection_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                **dict(row),
                "subscription_evidence": dict(audit or {}),
            }
            with self._rejection_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        except Exception as exc:
            self._rejection_write_failures += 1
            logger.warning("market_event_graph_live_source_rejection_write_failed err=%s", type(exc).__name__)


def canonical_live_universe_sha256(contract: LiveUniverseContract | Mapping[str, Any]) -> str:
    if isinstance(contract, LiveUniverseContract):
        return canonical_live_universe_sha256(
            {
                "schema_version": int(contract.schema_version),
                "broker_provider": str(contract.broker_provider or "").lower(),
                "token_domain": str(contract.token_domain or "").lower(),
                "name": contract.name,
                "version": contract.version,
                "effective_date": contract.effective_date or None,
                "source_retrieval_date": str(contract.source_retrieval_date or ""),
                "source_page_updated_date": contract.source_page_updated_date or None,
                "official_source_url": str(contract.official_source_url or ""),
                "official_raw_sha256": str(contract.official_raw_sha256 or ""),
                "index_symbol": contract.index_symbol,
                "index_instrument_token": contract.index_instrument_token,
                "provider_native_index_identifier": str(contract.provider_native_index_identifier or ""),
                "constituents": list(contract.constituents),
                "broker_instrument_master": {"sha256": str((contract.broker_instrument_master or {}).get("sha256") or "")},
            }
        )
    else:
        constituents = [
            {"symbol": str(row.get("symbol") or "").upper(), "instrument_token": int(row.get("instrument_token") or 0)}
            for row in contract.get("constituents", []) or []
        ]
        if contract.get("schema_version") is not None or contract.get("official_raw_sha256") is not None:
            payload = {
                "schema_version": int(contract.get("schema_version") or 1),
                "broker_provider": str(contract.get("broker_provider") or contract.get("token_domain") or "").lower(),
                "token_domain": str(contract.get("token_domain") or contract.get("broker_provider") or "").lower(),
                "name": str(contract.get("name") or ""),
                "version": str(contract.get("version") or ""),
                "effective_date": contract.get("effective_date"),
                "source_retrieval_date": str(contract.get("source_retrieval_date") or ""),
                "source_page_updated_date": contract.get("source_page_updated_date"),
            "official_source_url": str(contract.get("official_source_url") or ""),
            "official_raw_sha256": str(contract.get("official_raw_sha256") or ""),
            "index_symbol": str(contract.get("index_symbol") or "").upper(),
            "index_instrument_token": int(contract.get("index_instrument_token") or 0),
            "provider_native_index_identifier": str(contract.get("provider_native_index_identifier") or ""),
            "constituents": constituents,
            "broker_instrument_master": {"sha256": str((contract.get("broker_instrument_master") or {}).get("sha256") or "")},
        }
        else:
            payload = {
                "schema_version": 1,
                "broker_provider": "",
                "token_domain": "",
                "name": str(contract.get("name") or ""),
                "version": str(contract.get("version") or ""),
                "effective_date": str(contract.get("effective_date") or ""),
                "source_retrieval_date": "",
                "source_page_updated_date": "",
                "official_source_url": "",
                "official_raw_sha256": "",
                "index_symbol": str(contract.get("index_symbol") or "").upper(),
                "index_instrument_token": int(contract.get("index_instrument_token") or 0),
                "provider_native_index_identifier": str(contract.get("provider_native_index_identifier") or ""),
                "constituents": constituents,
                "source_provenance": str(contract.get("source_provenance") or ""),
                "broker_instrument_master": {},
            }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_live_constituent_subscription_audit() -> dict[str, Any]:
    bridge = LiveSourceRuntimeBridge()
    contract, reason = bridge._load_universe_contract()
    if contract is None:
        return {
            "verdict": reason,
            "subscription_request_succeeded_status": "UNPROVEN",
            "mode_request_succeeded_status": "UNPROVEN",
            "full_payload_observed_status": "UNPROVEN",
            "completed_bar_availability_status": "UNPROVEN",
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
    evidence = bridge._subscription_evidence(contract)
    ok, sub_reason, rejected = bridge._validate_subscription_evidence(contract, evidence)
    return {
        "verdict": "SUBSCRIPTION_EVIDENCE_READY" if ok else sub_reason,
        "universe_name": contract.name,
        "universe_version": contract.version,
        "universe_hash": contract.canonical_sha256,
        "requested_count": len([contract.index_symbol, *contract.constituent_symbols]),
        "subscription_request_succeeded_status": "APPLIED" if ok else "UNPROVEN",
        "mode_request_succeeded_status": "APPLIED" if ok else "UNPROVEN",
        "full_payload_observed_status": "APPLIED" if ok else "UNPROVEN",
        "missing_or_unapplied_identities": list(rejected),
        "subscription_evidence": dict(evidence),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _bar_end_epoch(bar: Mapping[str, Any], interval_seconds: int = 60) -> float | None:
    ts = bar.get("source_bar_end_epoch")
    if ts is not None:
        try:
            return float(ts)
        except Exception:
            return None
    start = bar.get("ts")
    if not isinstance(start, datetime):
        return None
    return float((start + timedelta(seconds=interval_seconds)).timestamp())


def _bar_has_live_provenance(
    bar: Mapping[str, Any],
    *,
    expected_symbol: str | None = None,
    expected_token: int | None = None,
    contract: LiveUniverseContract | None = None,
    subscription: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    prov = bar.get("bar_provenance")
    if not isinstance(prov, Mapping):
        return False, LIVE_BAR_PROVENANCE_UNPROVEN
    if str(prov.get("source_type") or "").lower() not in {"live_websocket", "tick_store_live"}:
        return False, LIVE_BAR_PROVENANCE_UNPROVEN
    if not str(prov.get("live_feed_session_id") or "").strip():
        return False, LIVE_BAR_PROVENANCE_UNPROVEN
    try:
        int(prov.get("reconnect_generation"))
    except Exception:
        return False, LIVE_BAR_PROVENANCE_UNPROVEN
    if bool(prov.get("historical_seed")) or bool(prov.get("replay_fixture")):
        return False, LIVE_BAR_PROVENANCE_UNPROVEN
    if bool(prov.get("non_live_fallback")) or bool(prov.get("recovered_synthetic")):
        return False, LIVE_BAR_PROVENANCE_UNPROVEN
    if prov.get("first_live_tick_epoch") is None or prov.get("last_live_tick_epoch") is None:
        return False, LIVE_BAR_PROVENANCE_UNPROVEN
    if contract is not None:
        if str(prov.get("provider") or "").lower() != str(contract.broker_provider or "").lower():
            return False, BAR_PROVIDER_MISMATCH
        if str(prov.get("token_domain") or "").lower() != str(contract.token_domain or "").lower():
            return False, BAR_TOKEN_DOMAIN_MISMATCH
        if str(prov.get("universe_hash") or "") != str(contract.canonical_sha256 or ""):
            return False, BAR_UNIVERSE_HASH_MISMATCH
    if subscription is not None:
        if str(prov.get("live_feed_session_id") or "") != str(subscription.get("feed_session_id") or ""):
            return False, FEED_SESSION_ID_MISMATCH
        try:
            if int(prov.get("reconnect_generation")) != int(subscription.get("reconnect_generation")):
                return False, RECONNECT_GENERATION_MISMATCH
        except Exception:
            return False, RECONNECT_GENERATION_MISMATCH
    if expected_symbol is not None and str(prov.get("symbol") or bar.get("symbol") or "").upper() != str(expected_symbol).upper():
        return False, BAR_SYMBOL_MISMATCH
    if expected_token is not None:
        try:
            if int(prov.get("instrument_token")) != int(expected_token):
                return False, BAR_INSTRUMENT_TOKEN_MISMATCH
        except Exception:
            return False, BAR_INSTRUMENT_TOKEN_MISMATCH
    return True, "OK"


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


_LIVE_SOURCE_BRIDGE: LiveSourceRuntimeBridge | None = None


def get_live_source_bridge() -> LiveSourceRuntimeBridge:
    global _LIVE_SOURCE_BRIDGE
    if _LIVE_SOURCE_BRIDGE is None:
        _LIVE_SOURCE_BRIDGE = LiveSourceRuntimeBridge()
    return _LIVE_SOURCE_BRIDGE


def flush_live_source_bridge() -> dict[str, Any]:
    if _LIVE_SOURCE_BRIDGE is None:
        return {
            "flushed": False,
            "write_failures": 0,
            "dropped_evidence_writes": 0,
            "max_queue_high_water_mark": 0,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
    return _LIVE_SOURCE_BRIDGE.flush()


def _flush_at_exit() -> None:
    try:
        if bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_FLUSH_ON_SHUTDOWN", True)):
            flush_live_source_bridge()
    except Exception as exc:
        logger.warning("market_event_graph_live_source_shutdown_flush_failed err=%s", type(exc).__name__)


atexit.register(_flush_at_exit)


__all__ = [
    "BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE",
    "BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION",
    "LIVE_BAR_PROVENANCE_UNPROVEN",
    "BAR_PROVIDER_MISMATCH",
    "BAR_TOKEN_DOMAIN_MISMATCH",
    "BAR_UNIVERSE_HASH_MISMATCH",
    "BAR_SYMBOL_MISMATCH",
    "BAR_INSTRUMENT_TOKEN_MISMATCH",
    "LIVE_UNIVERSE_NOT_CONFIGURED",
    "FEED_SESSION_ID_MISMATCH",
    "RECONNECT_GENERATION_MISMATCH",
    "PRE_GENERATION_TICK_PROVENANCE",
    "LiveSourceBridgeResult",
    "LiveSourceRuntimeBridge",
    "LiveUniverseContract",
    "build_live_constituent_subscription_audit",
    "canonical_live_universe_sha256",
    "BROKER_TOKEN_DOMAIN_MISMATCH",
    "flush_live_source_bridge",
    "get_live_source_bridge",
    "build_live_constituent_subscription_audit",
]
