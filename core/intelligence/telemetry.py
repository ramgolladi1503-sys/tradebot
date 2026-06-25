import json
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MIPTelemetry:
    """
    Structured telemetry emitter for the Market Intelligence Platform.
    Integrates logically alongside TradeBot's existing tracing.
    """
    def __init__(self, output_path: str = "logs/mip_telemetry.jsonl"):
        self.output_path = output_path

    def _emit(self, event_name: str, payload: Dict[str, Any]):
        # Enforce required schema
        base_payload = {
            "event_name": event_name,
            "timestamp": time.time(),
            "advisory_only": True
        }
        base_payload.update(payload)

        # Log to standard Python logger for dev stdout
        logger.info(f"MIP_TELEMETRY: {event_name} | {base_payload.get('source', 'unknown')} | {base_payload.get('status', 'info')}")

        # Persist to structured JSONL for observability agents (e.g. Datadog/Splunk)
        try:
            with open(self.output_path, 'a') as f:
                f.write(json.dumps(base_payload) + "\n")
        except Exception as e:
            logger.error(f"Failed to write telemetry: {e}")

    def emit_fetch_event(self, event_type: str, source: str, status: str,
                         duration: float = 0.0, failure_reason: Optional[str] = None):
        """Covers: fetch_started, fetch_succeeded, fetch_failed, robots_blocked, source_disabled"""
        self._emit(event_type, {
            "source": source,
            "status": status,
            "duration": duration,
            "failure_reason": failure_reason
        })

    def emit_extraction_event(self, event_type: str, source: str, status: str,
                              content_hash: Optional[str] = None):
        """Covers: extraction_started, extraction_succeeded, extraction_failed, duplicate_detected"""
        self._emit(event_type, {
            "source": source,
            "status": status,
            "content_hash": content_hash
        })

    def emit_storage_event(self, event_type: str, source: str, content_hash: str):
        """Covers: event_stored, factor_computed"""
        self._emit(event_type, {
            "source": source,
            "status": "success",
            "content_hash": content_hash
        })

    def emit_calibration_event(self, event_type: str, source: str, status: str):
        """Covers: replay_calibration_started, replay_calibration_insufficient"""
        self._emit(event_type, {
            "source": source,
            "status": status
        })

    def emit_integration_event(self, candidate_id: str):
        """Covers: advisory_context_attached"""
        self._emit("advisory_context_attached", {
            "source": "ContextAdapter",
            "status": "success",
            "candidate_id": candidate_id
        })
