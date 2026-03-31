from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'main.py'
ORCH = ROOT / 'core' / 'orchestrator.py'


def patch_main() -> None:
    text = MAIN.read_text()
    anchor = "    guard_result = auto_clear_risk_halt_if_safe()\n"
    block = """    guard_result = auto_clear_risk_halt_if_safe()\n    if exec_mode in {'SIM', 'PAPER', 'OFFLINE', 'BACKTEST'}:\n        try:\n            risk_halt.clear_halt()\n            print('[NONLIVE] cleared persisted risk halt for nonlive startup')\n        except Exception as exc:\n            print(f'[NONLIVE_WARN] failed_to_clear_risk_halt err={exc}')\n"""
    if "[NONLIVE] cleared persisted risk halt for nonlive startup" not in text:
        if anchor not in text:
            raise RuntimeError('Expected guard_result anchor not found in main.py')
        text = text.replace(anchor, block, 1)
    MAIN.write_text(text)


def patch_orchestrator() -> None:
    text = ORCH.read_text()

    logger_anchor = "logger = logging.getLogger(__name__)\n"
    helper_block = """


def _execution_mode_is_nonlive() -> bool:
    mode = str(getattr(cfg, 'EXECUTION_MODE', 'SIM') or 'SIM').strip().upper()
    return mode in {'SIM', 'PAPER', 'OFFLINE', 'BACKTEST'}
"""
    if "def _execution_mode_is_nonlive()" not in text:
        if logger_anchor not in text:
            raise RuntimeError('Expected logger anchor not found in orchestrator.py')
        text = text.replace(logger_anchor, logger_anchor + helper_block, 1)

    old_resolve = """def resolve_global_halt_reason(circuit_breaker) -> str | None:\n    \"\"\"\n    Authoritative runtime halt resolution.\n    Priority: manual kill switch -> persisted risk halt -> circuit breaker.\n    \"\"\"\n    if bool(getattr(cfg, \"KILL_SWITCH\", False)):\n        return \"KILL_SWITCH\"\n    try:\n        if risk_halt.is_halted():\n            return \"RISK_HALT\"\n    except Exception:\n        return \"RISK_HALT_STATE_ERROR\"\n    try:\n        if circuit_breaker and circuit_breaker.is_halted():\n            return str(circuit_breaker.halt_reason or \"CB_ACTIVE\")\n    except Exception:\n        return \"CB_STATE_ERROR\"\n    return None\n"""
    new_resolve = """def resolve_global_halt_reason(circuit_breaker) -> str | None:\n    \"\"\"\n    Authoritative runtime halt resolution.\n    Priority: manual kill switch -> persisted risk halt -> circuit breaker.\n    In nonlive modes we do not allow stale persisted halts to block the pipeline.\n    \"\"\"\n    if bool(getattr(cfg, \"KILL_SWITCH\", False)):\n        return \"KILL_SWITCH\"\n    try:\n        if risk_halt.is_halted():\n            if _execution_mode_is_nonlive():\n                logger.warning('nonlive_risk_halt_ignored')\n            else:\n                return \"RISK_HALT\"\n    except Exception:\n        return \"RISK_HALT_STATE_ERROR\"\n    try:\n        if circuit_breaker and circuit_breaker.is_halted():\n            if _execution_mode_is_nonlive():\n                logger.warning('nonlive_circuit_breaker_halt_ignored reason=%s', str(circuit_breaker.halt_reason or 'CB_ACTIVE'))\n            else:\n                return str(circuit_breaker.halt_reason or \"CB_ACTIVE\")\n    except Exception:\n        return \"CB_STATE_ERROR\"\n    return None\n"""
    if "nonlive_risk_halt_ignored" not in text:
        if old_resolve not in text:
            raise RuntimeError('Expected resolve_global_halt_reason block not found')
        text = text.replace(old_resolve, new_resolve, 1)

    old_latency = """    def _evaluate_latency_guard(self, *, market_open: bool, monitor_stats: dict) -> dict:\n        result = self.latency_guard.evaluate(\n            monitor_stats=monitor_stats or {},\n            market_open=bool(market_open),\n            now_ts=now_utc_epoch(),\n        )\n        state = {\n            \"action\": str(result.action),\n            \"reason\": str(result.reason),\n            \"cooldown_until_ts\": float(result.cooldown_until_ts or 0.0),\n            \"ts_epoch\": now_utc_epoch(),\n            \"blocks_new_entries\": bool(result.blocks_new_entries),\n            \"blocks_non_emergency_exits\": bool(result.blocks_non_emergency_exits),\n        }\n"""
    new_latency = """    def _evaluate_latency_guard(self, *, market_open: bool, monitor_stats: dict) -> dict:\n        if _execution_mode_is_nonlive():\n            state = {\n                \"action\": ACTION_OK,\n                \"reason\": \"nonlive_latency_guard_bypassed\",\n                \"cooldown_until_ts\": 0.0,\n                \"ts_epoch\": now_utc_epoch(),\n                \"blocks_new_entries\": False,\n                \"blocks_non_emergency_exits\": False,\n            }\n            self._latency_guard_state = state\n            self._latency_last_reported_action = ACTION_OK\n            return state\n        result = self.latency_guard.evaluate(\n            monitor_stats=monitor_stats or {},\n            market_open=bool(market_open),\n            now_ts=now_utc_epoch(),\n        )\n        state = {\n            \"action\": str(result.action),\n            \"reason\": str(result.reason),\n            \"cooldown_until_ts\": float(result.cooldown_until_ts or 0.0),\n            \"ts_epoch\": now_utc_epoch(),\n            \"blocks_new_entries\": bool(result.blocks_new_entries),\n            \"blocks_non_emergency_exits\": bool(result.blocks_non_emergency_exits),\n        }\n"""
    if "nonlive_latency_guard_bypassed" not in text:
        if old_latency not in text:
            raise RuntimeError('Expected _evaluate_latency_guard block not found')
        text = text.replace(old_latency, new_latency, 1)

    old_breakers = """    def _decision_breakers_block_entries(self) -> tuple[bool, list[str]]:\n        try:\n            blocked, reasons = self.decision_breakers.should_block_decisions(now_ts=now_utc_epoch())\n            if blocked:\n                mapped = [f\"decision_breaker_{str(r).lower()}\" for r in list(reasons or [])]\n                return True, mapped\n            return False, []\n        except Exception:\n            return False, []\n"""
    new_breakers = """    def _decision_breakers_block_entries(self) -> tuple[bool, list[str]]:\n        if _execution_mode_is_nonlive():\n            return False, []\n        try:\n            blocked, reasons = self.decision_breakers.should_block_decisions(now_ts=now_utc_epoch())\n            if blocked:\n                mapped = [f\"decision_breaker_{str(r).lower()}\" for r in list(reasons or [])]\n                return True, mapped\n            return False, []\n        except Exception:\n            return False, []\n"""
    if "if _execution_mode_is_nonlive():\n            return False, []" not in text:
        if old_breakers not in text:
            raise RuntimeError('Expected _decision_breakers_block_entries block not found')
        text = text.replace(old_breakers, new_breakers, 1)

    ORCH.write_text(text)


if __name__ == '__main__':
    patch_main()
    patch_orchestrator()
    print('Patched main.py and core/orchestrator.py for nonlive gate relaxation')
