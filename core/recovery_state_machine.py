import enum
from typing import Dict, Any

class RecoveryState(enum.Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    WS_LOSS = "WS_LOSS"
    AUTH_LOSS = "AUTH_LOSS"
    RECONNECTING = "RECONNECTING"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"
    FATAL = "FATAL"

def evaluate_feed_state(payload: Dict[str, Any]) -> RecoveryState:
    """
    Evaluates the raw feed payload to determine an explicit recovery state.
    Ambiguous states fail closed to FATAL.
    """
    if not isinstance(payload, dict):
        return RecoveryState.FATAL
        
    rstate = str(payload.get("feed_runtime_state") or payload.get("runtime_state") or "").upper()
    ws_state = str(payload.get("ws_lifecycle_state") or ("CONNECTED" if payload.get("ws_connected") else "")).upper()
    auth_state = str(payload.get("auth_state") or "").upper()
    recovery_blocked = bool(payload.get("recovery_blocked"))
    
    if rstate in {"FEED_LIFECYCLE_FATAL", "RECOVERY_BLOCKED", "RECONNECT_BLOCKED"}:
        return RecoveryState.FATAL
    if ws_state == "FATAL":
        return RecoveryState.FATAL
    if recovery_blocked:
        return RecoveryState.RECOVERY_BLOCKED
        
    if rstate == "AUTH_BLOCKED" or auth_state == "AUTH_REQUIRED":
        return RecoveryState.AUTH_LOSS
        
    if ws_state in {"CLOSED", "DISCONNECTED", "DROPPED"}:
        return RecoveryState.WS_LOSS
        
    if rstate == "RECONNECTING" or ws_state in {"CONNECTING", "RECONNECTING"}:
        return RecoveryState.RECONNECTING
        
    if rstate in {"HEALTHY", "RUNNING"} or (rstate == "" and ws_state in {"OPEN", "SUBSCRIBED", "CONNECTED"}):
        return RecoveryState.HEALTHY
        
    # Ambiguous
    if payload.get("status") == "healthy":
        return RecoveryState.HEALTHY
        
    return RecoveryState.FATAL

def is_fatal_state(state: RecoveryState) -> bool:
    """Returns True if the state requires the orchestrator to halt."""
    return state in {
        RecoveryState.FATAL, 
        RecoveryState.RECOVERY_BLOCKED
    }
