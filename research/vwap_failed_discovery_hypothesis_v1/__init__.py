"""Research-only VWAP failed-discovery hypothesis V1."""

from .detector import DEFAULT_CONFIG, Bar, DetectorConfig, FailedDiscoveryEvent, detect_failed_discoveries

__all__ = ["DEFAULT_CONFIG", "Bar", "DetectorConfig", "FailedDiscoveryEvent", "detect_failed_discoveries"]
