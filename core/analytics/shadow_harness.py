"""Governed Prospective Shadow Harness & Immutable Evidence Ledger.

Enforces:
  1. Operating Safety State:
     read_only=True, shadow_only=True, broker_write_authority=False,
     order_authority=False, paper_authorized=False, live_authorized=False.
  2. Complete separation of top-of-book QuotedExecutableProxy from actual fills
     (actual_fill_status is strictly ACTUAL_FILL_UNKNOWN in shadow observation).
  3. API Authority & Data Source Transparency:
     Tracks market_data_source (SYNTHETIC_TEST, HISTORICAL_REPLAY, BROKER_FEED, VENDOR_FEED)
     and actual runtime market_data_api_called boolean.
  4. Cryptographic Hash Chaining:
     prev_record_hash + canonical_payload_i hashing.
  5. Session Manifest Sealing with dynamic repo commit SHA + dirty-tree content hash.
"""

from __future__ import annotations
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Literal, Any

from core.analytics.cost_authority import CostAuthority, get_cost_authority, CostBreakdown
from core.analytics.revival_registry import CandidateFreezeManifest, RevivalRegistry

ActualFillStatus = Literal[
    "ACTUAL_FILL_UNKNOWN",
    "MISSING_REQUIRED_MARKET_DATA",
    "INVALID_STALE_QUOTE",
]

ObservationStatus = Literal[
    "VALID_RAW_OBSERVATION",
    "MISSING_REQUIRED_MARKET_DATA",
    "INVALID_STALE_QUOTE",
]

MarketDataSource = Literal[
    "SYNTHETIC_TEST",
    "HISTORICAL_REPLAY",
    "BROKER_FEED",
    "VENDOR_FEED",
]


def get_repo_code_identity(repo_root: Optional[Path] = None) -> Dict[str, str]:
    """Compute exact repository HEAD commit and dirty-tree content hash."""
    root = repo_root or Path("/Users/madhuram/tradebot")
    try:
        head_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(root), text=True
        ).strip()
    except Exception:
        head_sha = "UNKNOWN_NO_GIT"

    try:
        diff_bytes = subprocess.check_output(
            ["git", "diff", "HEAD"], cwd=str(root)
        )
        status_bytes = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(root)
        )
        combined = diff_bytes + status_bytes
        dirty_hash = hashlib.sha256(combined).hexdigest()
    except Exception:
        dirty_hash = "UNKNOWN_DIFF"

    return {
        "head_commit_sha": head_sha,
        "working_tree_content_hash": dirty_hash,
    }


@dataclass(frozen=True)
class QuotedExecutableProxy:
    """Conservative theoretical execution price based on prevailing top of book.

    Explicitly NOT an actual fill.
    """
    bid: float
    ask: float
    spread: float
    proxy_price: float      # Conservative: Ask for Long, Bid for Short
    quote_timestamp_ns: int
    quote_age_ms: int
    is_stale: bool
    depth_qty: Optional[int] = None


@dataclass(frozen=True)
class ShadowObservationRecord:
    """Immutable single observation record in cryptographic chain."""
    record_index: int
    prev_record_hash: str
    strategy_id: str
    candidate_version: str
    candidate_spec_sha256: str
    session_date: str
    signal_timestamp_ns: int
    direction: int          # +1 (Long), -1 (Short), 0 (No signal)
    observation_status: ObservationStatus
    market_data_source: MarketDataSource
    entry_quote_proxy: Optional[QuotedExecutableProxy]
    exit_quote_proxy: Optional[QuotedExecutableProxy]
    actual_fill_status: ActualFillStatus
    gross_move_pts: Optional[float]
    quoted_proxy_pnl_pts: Optional[float]
    cost_authority_id: Optional[str]
    cost_drag_pts: Optional[float]
    net_pnl_pts: Optional[float]
    market_data_api_called: bool
    broker_write_api_called: bool
    order_api_called: bool
    record_canonical_hash: str = ""

    def canonical_payload_dict(self) -> Dict[str, Any]:
        """Dictionary of fields contributing to record hash (excluding record_canonical_hash)."""
        entry_d = asdict(self.entry_quote_proxy) if self.entry_quote_proxy else None
        exit_d = asdict(self.exit_quote_proxy) if self.exit_quote_proxy else None
        return {
            "actual_fill_status": self.actual_fill_status,
            "broker_write_api_called": self.broker_write_api_called,
            "candidate_spec_sha256": self.candidate_spec_sha256,
            "candidate_version": self.candidate_version,
            "cost_authority_id": self.cost_authority_id,
            "cost_drag_pts": round(self.cost_drag_pts, 4) if self.cost_drag_pts is not None else None,
            "direction": self.direction,
            "entry_quote_proxy": entry_d,
            "exit_quote_proxy": exit_d,
            "gross_move_pts": round(self.gross_move_pts, 4) if self.gross_move_pts is not None else None,
            "market_data_api_called": self.market_data_api_called,
            "market_data_source": self.market_data_source,
            "net_pnl_pts": round(self.net_pnl_pts, 4) if self.net_pnl_pts is not None else None,
            "observation_status": self.observation_status,
            "order_api_called": self.order_api_called,
            "prev_record_hash": self.prev_record_hash,
            "quoted_proxy_pnl_pts": round(self.quoted_proxy_pnl_pts, 4) if self.quoted_proxy_pnl_pts is not None else None,
            "record_index": self.record_index,
            "session_date": self.session_date,
            "signal_timestamp_ns": self.signal_timestamp_ns,
            "strategy_id": self.strategy_id,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_payload_dict(), sort_keys=True, separators=(",", ":"))

    def compute_record_hash(self) -> str:
        payload = self.prev_record_hash + self.canonical_json()
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SessionManifest:
    manifest_version: str
    schema_version: str
    start_timestamp_ns: int
    end_timestamp_ns: int
    head_commit_sha: str
    working_tree_content_hash: str
    candidate_spec_hashes: Dict[str, str]
    data_source_ids: List[str]
    data_source_hashes: Dict[str, str]
    record_count: int
    genesis_hash: str
    final_chain_hash: str
    tamper_check: str
    safety_state: Dict[str, Any]

    def canonical_json(self) -> str:
        d = {
            "candidate_spec_hashes": {k: self.candidate_spec_hashes[k] for k in sorted(self.candidate_spec_hashes)},
            "data_source_hashes": {k: self.data_source_hashes[k] for k in sorted(self.data_source_hashes)},
            "data_source_ids": sorted(self.data_source_ids),
            "end_timestamp_ns": self.end_timestamp_ns,
            "final_chain_hash": self.final_chain_hash,
            "genesis_hash": self.genesis_hash,
            "head_commit_sha": self.head_commit_sha,
            "manifest_version": self.manifest_version,
            "record_count": self.record_count,
            "safety_state": {k: self.safety_state[k] for k in sorted(self.safety_state)},
            "schema_version": self.schema_version,
            "start_timestamp_ns": self.start_timestamp_ns,
            "tamper_check": self.tamper_check,
            "working_tree_content_hash": self.working_tree_content_hash,
        }
        return json.dumps(d, sort_keys=True, separators=(",", ":"))


class ReadOnlyMarketDataProvider:
    """Narrow interface for market data reads only. Rejects write-capable or mutable clients."""

    def __init__(self, feed_client: Any = None):
        # Fail closed: reject any client with order execution or portfolio write methods
        if feed_client is not None:
            forbidden = (
                "place_order", "modify_order", "cancel_order", "exit_order",
                "post", "put", "delete", "send_order", "submit", "execute"
            )
            for m in forbidden:
                if hasattr(feed_client, m):
                    raise PermissionError(
                        f"FATAL: ReadOnlyMarketDataProvider cannot wrap client exposing '{m}'"
                    )
        self.feed_client = feed_client

    def get_top_of_book(
        self,
        instrument: str,
        timestamp_ns: int,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        quote_timestamp_ns: Optional[int] = None,
        max_staleness_ms: int = 2000,
    ) -> Optional[QuotedExecutableProxy]:
        """Produce top-of-book proxy or None if missing."""
        if bid is None or ask is None:
            return None

        q_time = quote_timestamp_ns if quote_timestamp_ns is not None else timestamp_ns
        quote_age_ms = max(0, int((timestamp_ns - q_time) / 1_000_000))
        is_stale = quote_age_ms > max_staleness_ms

        spread = ask - bid
        return QuotedExecutableProxy(
            bid=bid,
            ask=ask,
            spread=spread,
            proxy_price=0.0,
            quote_timestamp_ns=q_time,
            quote_age_ms=quote_age_ms,
            is_stale=is_stale,
        )


class GovernedShadowLedger:
    """Append-only, hash-chained ledger for prospective shadow observations."""

    GENESIS_HASH = "0" * 64

    def __init__(
        self,
        registry: RevivalRegistry,
        market_data_provider: ReadOnlyMarketDataProvider,
        cost_authority_id: Optional[str] = None,
        repo_root: Optional[Path] = None,
    ):
        self.registry = registry
        self.market_data_provider = market_data_provider
        self.cost_authority_id = cost_authority_id
        self.cost_authority = get_cost_authority(cost_authority_id) if cost_authority_id else None
        self.repo_root = repo_root or Path("/Users/madhuram/tradebot")

        code_ident = get_repo_code_identity(self.repo_root)
        self.head_commit_sha = code_ident["head_commit_sha"]
        self.working_tree_content_hash = code_ident["working_tree_content_hash"]

        self.records: List[ShadowObservationRecord] = []
        self._current_chain_hash = self.GENESIS_HASH
        self._start_timestamp_ns = time.time_ns()

        # Mandatory operating safety state
        self.safety_state = {
            "read_only": True,
            "shadow_only": True,
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
            "ORDERS_PLACED": 0,
            "ORDERS_MODIFIED": 0,
            "ORDERS_CANCELLED": 0,
        }

    def record_observation(
        self,
        strategy_id: str,
        session_date: str,
        signal_timestamp_ns: int,
        direction: int,
        entry_bid: Optional[float],
        entry_ask: Optional[float],
        exit_bid: Optional[float],
        exit_ask: Optional[float],
        entry_quote_time_ns: Optional[int] = None,
        exit_quote_time_ns: Optional[int] = None,
        instrument_lot_size: int = 65,
        market_data_source: MarketDataSource = "SYNTHETIC_TEST",
        market_data_api_called: bool = False,
    ) -> ShadowObservationRecord:
        """Process and append a single shadow observation under strict fail-closed governance."""
        manifest = self.registry.get_manifest(strategy_id)
        if not manifest:
            raise ValueError(f"BLOCKED: Strategy {strategy_id} not registered in RevivalRegistry.")
        if manifest.queue != "QUEUE_1_SHADOW":
            raise ValueError(f"BLOCKED: Strategy {strategy_id} is in {manifest.queue}, not Queue 1.")
        if manifest.reconciliation_status != "RECONCILED_FOR_PROSPECTIVE_SHADOW":
            raise ValueError(
                f"BLOCKED_RECONCILIATION_REQUIRED: {strategy_id} status is {manifest.reconciliation_status}."
            )
        if not self.registry.verify_source_artifacts(strategy_id):
            raise ValueError(f"BLOCKED_AUTHORITY_CONFLICT: Source artifact hashes mismatch for {strategy_id}.")

        spec_hash = manifest.compute_spec_hash()

        obs_status: ObservationStatus = "VALID_RAW_OBSERVATION"
        entry_proxy: Optional[QuotedExecutableProxy] = None
        exit_proxy: Optional[QuotedExecutableProxy] = None
        gross_move_pts: Optional[float] = None
        quoted_proxy_pnl_pts: Optional[float] = None
        cost_drag_pts: Optional[float] = None
        net_pnl_pts: Optional[float] = None

        if direction != 0:
            if entry_bid is None or entry_ask is None:
                obs_status = "MISSING_REQUIRED_MARKET_DATA"
            else:
                raw_entry = self.market_data_provider.get_top_of_book(
                    instrument=manifest.instrument_semantics,
                    timestamp_ns=signal_timestamp_ns,
                    bid=entry_bid,
                    ask=entry_ask,
                    quote_timestamp_ns=entry_quote_time_ns,
                )
                if raw_entry.is_stale:
                    obs_status = "INVALID_STALE_QUOTE"
                else:
                    proxy_px = raw_entry.ask if direction > 0 else raw_entry.bid
                    entry_proxy = QuotedExecutableProxy(
                        bid=raw_entry.bid,
                        ask=raw_entry.ask,
                        spread=raw_entry.spread,
                        proxy_price=proxy_px,
                        quote_timestamp_ns=raw_entry.quote_timestamp_ns,
                        quote_age_ms=raw_entry.quote_age_ms,
                        is_stale=False,
                    )

            if exit_bid is not None and exit_ask is not None and obs_status == "VALID_RAW_OBSERVATION":
                exit_time_ns = exit_quote_time_ns or signal_timestamp_ns
                raw_exit = self.market_data_provider.get_top_of_book(
                    instrument=manifest.instrument_semantics,
                    timestamp_ns=exit_time_ns,
                    bid=exit_bid,
                    ask=exit_ask,
                    quote_timestamp_ns=exit_time_ns,
                )
                if raw_exit.is_stale:
                    obs_status = "INVALID_STALE_QUOTE"
                else:
                    exit_px = raw_exit.bid if direction > 0 else raw_exit.ask
                    exit_proxy = QuotedExecutableProxy(
                        bid=raw_exit.bid,
                        ask=raw_exit.ask,
                        spread=raw_exit.spread,
                        proxy_price=exit_px,
                        quote_timestamp_ns=raw_exit.quote_timestamp_ns,
                        quote_age_ms=raw_exit.quote_age_ms,
                        is_stale=False,
                    )

            if obs_status == "VALID_RAW_OBSERVATION" and entry_proxy and exit_proxy:
                entry_mid = (entry_proxy.bid + entry_proxy.ask) / 2.0
                exit_mid = (exit_proxy.bid + exit_proxy.ask) / 2.0
                gross_move_pts = (exit_mid - entry_mid) * direction
                quoted_proxy_pnl_pts = (exit_proxy.proxy_price - entry_proxy.proxy_price) * direction

                if self.cost_authority is not None and self.cost_authority.verification_status == "COST_AUTHORITY_VERIFIED":
                    side_str = "LONG" if direction > 0 else "SHORT"
                    breakdown = self.cost_authority.compute_futures_cost(
                        entry_px=entry_proxy.proxy_price,
                        exit_px=exit_proxy.proxy_price,
                        side=side_str,
                        lot_size=instrument_lot_size,
                    )
                    if breakdown is not None:
                        cost_drag_pts = breakdown.total_friction_pts
                        net_pnl_pts = quoted_proxy_pnl_pts - cost_drag_pts

        record_idx = len(self.records)
        record = ShadowObservationRecord(
            record_index=record_idx,
            prev_record_hash=self._current_chain_hash,
            strategy_id=strategy_id,
            candidate_version=manifest.candidate_version,
            candidate_spec_sha256=spec_hash,
            session_date=session_date,
            signal_timestamp_ns=signal_timestamp_ns,
            direction=direction,
            observation_status=obs_status,
            market_data_source=market_data_source,
            entry_quote_proxy=entry_proxy,
            exit_quote_proxy=exit_proxy,
            actual_fill_status="ACTUAL_FILL_UNKNOWN",
            gross_move_pts=gross_move_pts,
            quoted_proxy_pnl_pts=quoted_proxy_pnl_pts,
            cost_authority_id=self.cost_authority_id if self.cost_authority else None,
            cost_drag_pts=cost_drag_pts,
            net_pnl_pts=net_pnl_pts,
            market_data_api_called=market_data_api_called,
            broker_write_api_called=False,
            order_api_called=False,
        )

        canonical_hash = record.compute_record_hash()
        sealed_record = ShadowObservationRecord(
            record_index=record.record_index,
            prev_record_hash=record.prev_record_hash,
            strategy_id=record.strategy_id,
            candidate_version=record.candidate_version,
            candidate_spec_sha256=record.candidate_spec_sha256,
            session_date=record.session_date,
            signal_timestamp_ns=record.signal_timestamp_ns,
            direction=record.direction,
            observation_status=record.observation_status,
            market_data_source=record.market_data_source,
            entry_quote_proxy=record.entry_quote_proxy,
            exit_quote_proxy=record.exit_quote_proxy,
            actual_fill_status=record.actual_fill_status,
            gross_move_pts=record.gross_move_pts,
            quoted_proxy_pnl_pts=record.quoted_proxy_pnl_pts,
            cost_authority_id=record.cost_authority_id,
            cost_drag_pts=record.cost_drag_pts,
            net_pnl_pts=record.net_pnl_pts,
            market_data_api_called=record.market_data_api_called,
            broker_write_api_called=record.broker_write_api_called,
            order_api_called=record.order_api_called,
            record_canonical_hash=canonical_hash,
        )

        self.records.append(sealed_record)
        self._current_chain_hash = canonical_hash
        return sealed_record

    def verify_chain_integrity(self) -> bool:
        """Recompute every link in the cryptographic chain to verify zero mutations."""
        expected_prev = self.GENESIS_HASH
        for idx, rec in enumerate(self.records):
            if rec.record_index != idx:
                return False
            if rec.prev_record_hash != expected_prev:
                return False
            computed_hash = rec.compute_record_hash()
            if rec.record_canonical_hash != computed_hash:
                return False
            expected_prev = computed_hash
        return True

    def seal_session(self) -> SessionManifest:
        """Finalize and seal the session manifest with cryptographic tamper check."""
        if not self.verify_chain_integrity():
            raise RuntimeError("FATAL: Chain integrity check failed during session seal.")

        reconciled = self.registry.get_reconciled_queue_1_candidates()
        spec_hashes = {m.strategy_id: m.compute_spec_hash() for m in reconciled}
        data_ids = []
        data_hashes = {}
        for m in reconciled:
            data_ids.extend(m.data_source_ids)
            data_hashes.update(m.data_source_sha256s)

        manifest = SessionManifest(
            manifest_version="1.0.0",
            schema_version="1.0.0",
            start_timestamp_ns=self._start_timestamp_ns,
            end_timestamp_ns=time.time_ns(),
            head_commit_sha=self.head_commit_sha,
            working_tree_content_hash=self.working_tree_content_hash,
            candidate_spec_hashes=spec_hashes,
            data_source_ids=sorted(list(set(data_ids))),
            data_source_hashes=data_hashes,
            record_count=len(self.records),
            genesis_hash=self.GENESIS_HASH,
            final_chain_hash=self._current_chain_hash,
            tamper_check="VERIFIED_IMMUTABLE",
            safety_state=self.safety_state,
        )
        return manifest
