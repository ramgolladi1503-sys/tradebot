from dataclasses import dataclass
from core.feed_state_model import FeedSnapshot, FeedVerdict, FeedLifecycleState

@dataclass(frozen=True)
class RestartPolicyDecision:
    restart_required: bool
    restart_reason: str
    should_sleep: bool = False
    sleep_reason: str = ""

def evaluate_restart_policy(snapshot: FeedSnapshot, verdict: FeedVerdict) -> RestartPolicyDecision:
    if snapshot.process_restart_required:
        return RestartPolicyDecision(
            restart_required=True,
            restart_reason="process_restart_flag_set",
        )
        
    if verdict.lifecycle_state == FeedLifecycleState.RESTART_REQUIRED:
        return RestartPolicyDecision(
            restart_required=True,
            restart_reason=f"lifecycle_restart_required: {verdict.reason_code}",
        )
        
    if verdict.lifecycle_state == FeedLifecycleState.MARKET_CLOSED:
        return RestartPolicyDecision(
            restart_required=False,
            restart_reason="market_closed",
            should_sleep=True,
            sleep_reason="market_closed",
        )

    # DOWN alone is not fatal unless the process forces a restart
    if not snapshot.effective_ws_connected and verdict.lifecycle_state == FeedLifecycleState.DEGRADED:
        return RestartPolicyDecision(
            restart_required=False,
            restart_reason="degraded_ws_disconnected",
        )
        
    return RestartPolicyDecision(
        restart_required=False,
        restart_reason="OK",
    )
