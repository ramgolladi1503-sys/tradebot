import json
from typing import List, Optional
from pathlib import Path

from .evidence_models import OptionTracePoint


class OptionTraceAdapter:
    """Reads historical option price traces and provides alignment capabilities."""

    def __init__(self, trace_file: Path):
        self.trace_file = Path(trace_file)
        self._traces: List[OptionTracePoint] = []
        self._loaded = False

    def _load_if_needed(self):
        if self._loaded:
            return
        if not self.trace_file.exists():
            self._loaded = True
            return

        with self.trace_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    point = OptionTracePoint(
                        timestamp=float(data.get("timestamp", 0.0)),
                        ltp=float(data.get("ltp") or data.get("close", 0.0)),
                        bid=data.get("bid"),
                        ask=data.get("ask"),
                        volume=data.get("volume"),
                        oi=data.get("oi"),
                        spread=data.get("spread")
                    )
                    if point.timestamp > 0 and point.ltp > 0:
                        self._traces.append(point)
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
                    
        # Ensure chronological order
        self._traces.sort(key=lambda p: p.timestamp)
        self._loaded = True

    def get_trace_window(self, start_time: float, end_time: Optional[float] = None) -> List[OptionTracePoint]:
        """Get traces between start_time and end_time (inclusive)."""
        self._load_if_needed()
        if not self._traces:
            return []

        # Simple linear search for now; can optimize with bisect if needed
        window = []
        for point in self._traces:
            if point.timestamp >= start_time:
                if end_time is not None and point.timestamp > end_time:
                    break
                window.append(point)
        return window

    def get_nearest_forward_tick(self, timestamp: float, max_gap_seconds: float = 60.0) -> Optional[OptionTracePoint]:
        """Find the exact or nearest tick after the given timestamp, within max_gap_seconds."""
        self._load_if_needed()
        if not self._traces:
            return None

        for point in self._traces:
            if point.timestamp >= timestamp:
                if point.timestamp - timestamp <= max_gap_seconds:
                    return point
                return None
        return None

    def has_data(self) -> bool:
        self._load_if_needed()
        return len(self._traces) > 0
