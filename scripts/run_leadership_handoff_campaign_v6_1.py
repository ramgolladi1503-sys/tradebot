#!/usr/bin/env python3
"""V6.1 repair: bind leadership-handoff campaign to the corrected delayed-entry refresh."""
from __future__ import annotations

from scripts import run_leadership_handoff_campaign_v6 as campaign
from scripts import run_peer_reclaim_horizon_campaign_v5_1 as fixed

campaign.horizon.shift_signal_entry = fixed.shift_signal_entry


if __name__ == "__main__":
    raise SystemExit(campaign.main())
