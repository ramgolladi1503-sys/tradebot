from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


SUBSCRIPTION_TRUTH_CONTRACT_SCHEMA_VERSION = 1
SUBSCRIPTION_TRUTH_CONTRACT_SOURCE = "subscription_truth_contract_v1"

SUBSCRIPTION_TRUTH_OK = "SUBSCRIPTION_TRUTH_OK"
SUBSCRIPTION_TRUTH_BLOCKED = "SUBSCRIPTION_TRUTH_BLOCKED"
SUBSCRIPTION_TRUTH_RESUBSCRIBE_REQUIRED = "RESUBSCRIBE_REQUIRED"
SUBSCRIPTION_TRUTH_RESUBSCRIBE_VERIFIED = "RESUBSCRIBE_VERIFIED"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class SubscriptionTruthContract:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    truth_state: str
    subscription_truth_ok: bool
    resubscribe_verified: bool
    intended_tokens_count: int
    subscribed_tokens_count: int
    subscribed_option_tokens_count: int
    missing_option_tokens_count: int
    verified_option_symbols: tuple[str, ...]
    missing_option_symbols: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verified_option_symbols"] = list(self.verified_option_symbols)
        payload["missing_option_symbols"] = list(self.missing_option_symbols)
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_symbols(value: Any) -> tuple[str, ...]:
    if value in (None, "", "None"):
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(sorted({str(item).strip().upper() for item in value if str(item).strip()}))
    text = str(value).strip().upper()
    return (text,) if text else ()


def _dedupe(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item).strip().upper() for item in items if str(item).strip()))


def build_subscription_truth_contract(payload: Mapping[str, Any] | None) -> SubscriptionTruthContract:
    source = _as_mapping(payload)
    runtime = _as_mapping(source.get("feed_runtime") or source.get("runtime") or source)
    state = _upper(source.get("subscription_state") or runtime.get("subscription_state") or runtime.get("state") or source.get("state"))
    verification_state = _upper(source.get("verification_state") or runtime.get("verification_state"))

    intended_tokens_count = _as_int(source.get("intended_tokens_count") or runtime.get("intended_tokens_count"))
    subscribed_tokens_count = _as_int(source.get("subscribed_tokens_count") or runtime.get("subscribed_tokens_count"))
    subscribed_option_tokens_count = _as_int(source.get("subscribed_option_tokens_count") or runtime.get("subscribed_option_tokens_count"))
    missing_option_tokens_count = _as_int(source.get("missing_option_tokens_count") or runtime.get("missing_option_tokens_count"))
    verified_option_symbols = _normalize_symbols(source.get("verified_option_symbols") or runtime.get("verified_option_symbols"))
    missing_option_symbols = _normalize_symbols(source.get("missing_option_symbols") or runtime.get("missing_option_symbols"))
    resubscribe_attempted = bool(source.get("resubscribe_attempted") or runtime.get("resubscribe_attempted"))
    resubscribe_successful = source.get("resubscribe_successful")
    if resubscribe_successful is None:
        resubscribe_successful = runtime.get("resubscribe_successful")
    if isinstance(resubscribe_successful, bool):
        resubscribe_successful_bool = resubscribe_successful
    else:
        resubscribe_successful_bool = None
    option_reason_map = _as_mapping(source.get("option_feed_block_reason_by_symbol") or runtime.get("option_feed_block_reason_by_symbol"))
    option_blockers = tuple(
        sorted(
            {
                _upper(value)
                for value in option_reason_map.values()
                if _upper(value) not in {"", "OK", "NONE", "HEALTHY", "FRESH"}
            }
        )
    )
    token_ages = _as_mapping(source.get("option_last_tick_age_by_symbol") or runtime.get("option_last_tick_age_by_symbol"))

    blockers: list[str] = []
    warnings: list[str] = []

    if state in {"AUTH_REQUIRED", "RESTART_REQUIRED"}:
        blockers.append(state)
    if intended_tokens_count > 0 and subscribed_tokens_count <= 0:
        blockers.append("NO_SUBSCRIBED_TOKENS")
    if intended_tokens_count > 0 and subscribed_option_tokens_count <= 0:
        blockers.append("NO_SUBSCRIBED_OPTION_TOKENS")
    if missing_option_tokens_count > 0:
        blockers.append("MISSING_OPTION_TOKENS")
    if missing_option_symbols:
        blockers.append("MISSING_OPTION_SYMBOLS")
    if option_blockers:
        blockers.append("OPTION_FEED_BLOCKED")

    verified_complete = (
        intended_tokens_count > 0
        and subscribed_tokens_count >= intended_tokens_count
        and subscribed_option_tokens_count > 0
        and not missing_option_tokens_count
        and not missing_option_symbols
        and not option_blockers
    )
    if verification_state in {"VERIFYING", "PENDING", "IN_PROGRESS"}:
        warnings.append("SUBSCRIPTION_VERIFICATION_IN_PROGRESS")
    if resubscribe_attempted and resubscribe_successful_bool is False:
        blockers.append("RESUBSCRIBE_FAILED")
    if resubscribe_attempted and resubscribe_successful_bool is True and verified_complete:
        warnings.append(SUBSCRIPTION_TRUTH_RESUBSCRIBE_VERIFIED)

    subscription_truth_ok = not blockers and verified_complete
    resubscribe_verified = bool(resubscribe_attempted and resubscribe_successful_bool is True and verified_complete)

    if subscription_truth_ok:
        truth_state = SUBSCRIPTION_TRUTH_OK if not resubscribe_attempted else SUBSCRIPTION_TRUTH_RESUBSCRIBE_VERIFIED
    elif blockers:
        truth_state = SUBSCRIPTION_TRUTH_BLOCKED
    else:
        truth_state = SUBSCRIPTION_TRUTH_RESUBSCRIBE_REQUIRED
        warnings.append("SUBSCRIPTION_VERIFICATION_REQUIRED")

    return SubscriptionTruthContract(
        schema_version=SUBSCRIPTION_TRUTH_CONTRACT_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=SUBSCRIPTION_TRUTH_CONTRACT_SOURCE,
        truth_state=truth_state,
        subscription_truth_ok=subscription_truth_ok,
        resubscribe_verified=resubscribe_verified,
        intended_tokens_count=intended_tokens_count,
        subscribed_tokens_count=subscribed_tokens_count,
        subscribed_option_tokens_count=subscribed_option_tokens_count,
        missing_option_tokens_count=missing_option_tokens_count,
        verified_option_symbols=verified_option_symbols,
        missing_option_symbols=missing_option_symbols,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "does_not_mutate_runtime": True,
            "does_not_resubscribe": True,
            "does_not_call_broker": True,
            "does_not_place_orders": True,
            "token_age_symbol_count": len(token_ages),
        },
    )


__all__ = [
    "SUBSCRIPTION_TRUTH_BLOCKED",
    "SUBSCRIPTION_TRUTH_CONTRACT_SOURCE",
    "SUBSCRIPTION_TRUTH_CONTRACT_SCHEMA_VERSION",
    "SUBSCRIPTION_TRUTH_OK",
    "SUBSCRIPTION_TRUTH_RESUBSCRIBE_REQUIRED",
    "SUBSCRIPTION_TRUTH_RESUBSCRIBE_VERIFIED",
    "SubscriptionTruthContract",
    "build_subscription_truth_contract",
]
