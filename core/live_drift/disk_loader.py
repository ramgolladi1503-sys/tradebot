import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from core.live_drift.drift_models import CertifiedBaseline, LiveSnapshot
from core.live_drift.drift_errors import LiveDriftInputMissingError, InvalidBaselineError, InvalidSnapshotError

class DiskLiveDriftLoader:
    def _reject_duplicate_keys(self, ordered_pairs):
        """Reject JSON objects with duplicate keys."""
        d = {}
        for k, v in ordered_pairs:
            if k in d:
                raise ValueError(f"Duplicate key: {k}")
            d[k] = v
        return d

    def _validate_common(self, data: Dict[str, Any], strategy_id: str, is_baseline: bool) -> None:
        error_class = InvalidBaselineError if is_baseline else InvalidSnapshotError
        
        if "strategy_id" not in data:
            raise error_class("Missing strategy_id")
        if data["strategy_id"] != strategy_id:
            raise error_class(f"strategy_id mismatch: expected {strategy_id}, got {data['strategy_id']}")
            
        if "schema_version" not in data:
            raise error_class("Missing schema_version")
        if data["schema_version"] not in ["1.0", "1.1"]:
            raise error_class(f"Unsupported schema version: {data['schema_version']}")

    def load_baseline(self, strategy_id: str) -> CertifiedBaseline:
        path = os.path.join("data", "live_drift", "baselines", f"{strategy_id}.json")
        if not os.path.exists(path):
            raise LiveDriftInputMissingError(f"Missing certification baseline: {path}")
        
        try:
            with open(path, "r") as f:
                data = json.load(f, object_pairs_hook=self._reject_duplicate_keys)
        except json.JSONDecodeError as e:
            raise InvalidBaselineError(f"Malformed JSON: {e}")
        except ValueError as e:
            raise InvalidBaselineError(str(e))
            
        self._validate_common(data, strategy_id, is_baseline=True)
        
        if "certification_id" not in data:
            raise InvalidBaselineError("Missing certification_id")
            
        required_fields = ["certified_timestamp", "expected_expectancy", "expected_profit_factor", "max_drawdown_limit", "regime_signature"]
        for field in required_fields:
            if field not in data:
                raise InvalidBaselineError(f"Missing required field: {field}")
                
        try:
            timestamp = datetime.fromisoformat(data["certified_timestamp"])
            if not timestamp.tzinfo:
                # Require timezone aware or assume UTC
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            raise InvalidBaselineError(f"Invalid timestamp: {data['certified_timestamp']}")

        return CertifiedBaseline(
            strategy_id=data["strategy_id"],
            certification_id=data["certification_id"],
            certified_timestamp=timestamp,
            expected_expectancy=float(data["expected_expectancy"]),
            expected_profit_factor=float(data["expected_profit_factor"]),
            max_drawdown_limit=float(data["max_drawdown_limit"]),
            regime_signature=str(data["regime_signature"])
        )
        
    def load_snapshot(self, strategy_id: str) -> LiveSnapshot:
        path = os.path.join("data", "live_drift", "snapshots", f"{strategy_id}.json")
        if not os.path.exists(path):
            raise LiveDriftInputMissingError(f"Missing live snapshot: {path}")
            
        try:
            with open(path, "r") as f:
                data = json.load(f, object_pairs_hook=self._reject_duplicate_keys)
        except json.JSONDecodeError as e:
            raise InvalidSnapshotError(f"Malformed JSON: {e}")
        except ValueError as e:
            raise InvalidSnapshotError(str(e))
            
        self._validate_common(data, strategy_id, is_baseline=False)
            
        required_fields = [
            "snapshot_timestamp", "observed_expectancy", "observed_profit_factor", 
            "current_drawdown", "current_regime_signature", "slippage_ratio", 
            "total_observations", "data_freshness_seconds"
        ]
        for field in required_fields:
            if field not in data:
                raise InvalidSnapshotError(f"Missing required field: {field}")

        try:
            timestamp = datetime.fromisoformat(data["snapshot_timestamp"])
            if not timestamp.tzinfo:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            raise InvalidSnapshotError(f"Invalid timestamp: {data['snapshot_timestamp']}")

        return LiveSnapshot(
            strategy_id=data["strategy_id"],
            snapshot_timestamp=timestamp,
            observed_expectancy=float(data["observed_expectancy"]),
            observed_profit_factor=float(data["observed_profit_factor"]),
            current_drawdown=float(data["current_drawdown"]),
            current_regime_signature=str(data["current_regime_signature"]),
            slippage_ratio=float(data["slippage_ratio"]),
            total_observations=int(data["total_observations"]),
            data_freshness_seconds=int(data["data_freshness_seconds"])
        )
