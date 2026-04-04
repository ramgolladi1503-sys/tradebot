from __future__ import annotations

import logging
import time
from typing import Any

from config import config as cfg
from core.execution_router import ExecutionRouter
from core.orders.execution_plan import ExecutionPlan

from core.brokers.openalgo_client import (
    OpenAlgoClient,
    OpenAlgoApiError,
    OpenAlgoConfigError,
    OpenAlgoHttpError,
    build_openalgo_order_request,
)

logger = logging.getLogger(__name__)


class OpenAlgoExecutionRouter(ExecutionRouter):
    """
    Drop-in replacement for ExecutionRouter that routes LIVE orders via OpenAlgo.

    SIM/PAPER paths delegate to the base router.
    LIVE path uses ExecutionEngine.place_order_from_plan with an OpenAlgo submit function.
    """

    def __init__(self, *, feed_health=None) -> None:
        super().__init__(feed_health=feed_health)
        self._client: OpenAlgoClient | None = None

    def _get_client(self) -> OpenAlgoClient:
        if self._client is None:
            self._client = OpenAlgoClient()
        return self._client

    def _openalgo_submit(self, plan: ExecutionPlan, trade: Any):
        client = self._get_client()
        order_req = build_openalgo_order_request(trade)

        def _submit():
            result = client.place_order(order_req)
            return {
                "orderid": result.get("order_id"),
                "status": result.get("status"),
                "raw": result.get("raw"),
            }

        return self.engine.place_order_from_plan(
            plan,
            submit_order_fn=_submit,
            submit_kwargs={},
        )

    def execute(
        self,
        trade,
        bid,
        ask,
        volume,
        depth=None,
        snapshot_fn=None,
        spread_pct=None,
        depth_imbalance=None,
        vol_z=None,
    ):
        mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()

        # Delegate SIM/PAPER unchanged
        if mode in {"SIM", "PAPER"}:
            return super().execute(
                trade,
                bid,
                ask,
                volume,
                depth=depth,
                snapshot_fn=snapshot_fn,
                spread_pct=spread_pct,
                depth_imbalance=depth_imbalance,
                vol_z=vol_z,
            )

        # LIVE path via OpenAlgo
        if mode == "LIVE":
            if not OpenAlgoClient.enabled():
                # fall back to base (which will likely abort)
                return super().execute(
                    trade,
                    bid,
                    ask,
                    volume,
                    depth=depth,
                    snapshot_fn=snapshot_fn,
                    spread_pct=spread_pct,
                    depth_imbalance=depth_imbalance,
                    vol_z=vol_z,
                )

            try:
                plan = ExecutionPlan.from_trade(trade, mode=mode)
                started = time.time()
                out = self._openalgo_submit(plan, trade)
                latency_ms = round((time.time() - started) * 1000.0, 2)
                placed = bool(out.get("placed"))
                reason = out.get("reason")
                report = {
                    "placed": placed,
                    "latency_ms": latency_ms,
                    "reason": reason,
                    "snapshot_id": plan.snapshot_id,
                    "decision_id": plan.decision_id,
                }
                return placed, None, report
            except (OpenAlgoConfigError, OpenAlgoApiError, OpenAlgoHttpError) as exc:
                logger.error("openalgo_execution_error err=%s:%s", type(exc).__name__, exc)
                return False, None, {"reason_if_aborted": f"openalgo_error:{type(exc).__name__}"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("openalgo_execution_unexpected err=%s", exc)
                return False, None, {"reason_if_aborted": "openalgo_unexpected_error"}

        # Unknown mode -> base
        return super().execute(
            trade,
            bid,
            ask,
            volume,
            depth=depth,
            snapshot_fn=snapshot_fn,
            spread_pct=spread_pct,
            depth_imbalance=depth_imbalance,
            vol_z=vol_z,
        )
