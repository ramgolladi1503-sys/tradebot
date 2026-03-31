from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADE_BUILDER = ROOT / 'strategies' / 'trade_builder.py'


def patch_trade_builder() -> None:
    text = TRADE_BUILDER.read_text()

    old = """        intent = self.trade_intent_flags(market_data, opt=chosen_opt)\n        intent[\"planning_only\"] = True\n        intent[\"execution_allowed\"] = False\n        intent[\"execution_reason\"] = trigger_reason\n        source_flags = dict(intent.get(\"source_flags\") or {})\n"""
    new = """        intent = self.trade_intent_flags(market_data, opt=chosen_opt)\n        current_mode = str(\n            market_data.get(\"execution_mode\")\n            or ((market_data.get(\"market_context\") or {}).get(\"execution_mode\") if isinstance(market_data.get(\"market_context\"), dict) else \"\")\n            or getattr(cfg, \"EXECUTION_MODE\", \"SIM\")\n        ).strip().upper()\n        allow_nonlive_executable = bool(getattr(cfg, \"NONLIVE_OPPORTUNITY_EXECUTION_ENABLE\", True))\n        min_exec_quality = float(getattr(cfg, \"NONLIVE_OPPORTUNITY_EXECUTION_MIN_SCORE\", 0.34))\n        executable_nonlive = bool(\n            allow_nonlive_executable\n            and current_mode in {\"SIM\", \"PAPER\", \"OFFHOURS\"}\n            and float(candidate_quality_score) >= float(min_exec_quality)\n        )\n        intent[\"planning_only\"] = False if executable_nonlive else True\n        intent[\"execution_allowed\"] = bool(executable_nonlive)\n        intent[\"execution_reason\"] = (\"nonlive_opportunity_executable\" if executable_nonlive else trigger_reason)\n        source_flags = dict(intent.get(\"source_flags\") or {})\n        source_flags[\"nonlive_opportunity_executable\"] = bool(executable_nonlive)\n        source_flags[\"nonlive_opportunity_min_exec_quality\"] = round(float(min_exec_quality), 6)\n"""
    if 'nonlive_opportunity_executable' not in text:
        if old not in text:
            raise RuntimeError('Expected nonlive advisory block not found in trade_builder.py')
        text = text.replace(old, new, 1)

    old2 = '            candidate_status="advisory_only",\n            permission="ADVISORY_ONLY",\n            permission_reason=trigger_reason,\n'
    new2 = '            candidate_status=("executable" if executable_nonlive else "advisory_only"),\n            permission=("EXECUTE" if executable_nonlive else "ADVISORY_ONLY"),\n            permission_reason=("nonlive_opportunity_executable" if executable_nonlive else trigger_reason),\n'
    if 'candidate_status=("executable" if executable_nonlive else "advisory_only")' not in text:
        if old2 not in text:
            raise RuntimeError('Expected candidate status block not found in trade_builder.py')
        text = text.replace(old2, new2, 1)

    TRADE_BUILDER.write_text(text)


if __name__ == '__main__':
    patch_trade_builder()
    print('Patched strategies/trade_builder.py for nonlive executable opportunity fallback')
