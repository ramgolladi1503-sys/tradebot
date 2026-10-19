from __future__ import annotations

from typing import Any

from .campaign import CompressionCampaignConfig, CompressionCampaignResult
from .identity import rebind_campaign_identity, rebind_ledger_identity
from .safe_campaign import run_compression_campaign_safe as _run_compression_campaign
from .signal_ledger import (
    CompressionLedgerConfig,
    CompressionSignalLedgerResult,
    build_compression_signal_ledger as _build_compression_signal_ledger,
)
from .splits import build_chronological_split_manifest


def build_compression_signal_ledger(
    *args: Any,
    **kwargs: Any,
) -> CompressionSignalLedgerResult:
    result = _build_compression_signal_ledger(*args, **kwargs)
    rebound, _ = rebind_ledger_identity(result)
    return rebound


def run_compression_campaign(
    *args: Any,
    **kwargs: Any,
) -> CompressionCampaignResult:
    return rebind_campaign_identity(
        _run_compression_campaign(*args, **kwargs)
    )


__all__ = [
    "CompressionCampaignConfig",
    "CompressionCampaignResult",
    "CompressionLedgerConfig",
    "CompressionSignalLedgerResult",
    "build_chronological_split_manifest",
    "build_compression_signal_ledger",
    "run_compression_campaign",
]
