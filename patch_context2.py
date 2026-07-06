with open("core/movement_regime.py", "r") as f:
    text = f.read()
text = text.replace("ctx = StrategyContext(**ctx)", "from core.movement_contract import context_from_dict\n            ctx = context_from_dict(ctx)")
with open("core/movement_regime.py", "w") as f:
    f.write(text)

with open("core/movement_registry.py", "r") as f:
    text = f.read()
text = text.replace("ctx = context if isinstance(context, StrategyContext) else StrategyContext(**context)", "from core.movement_contract import context_from_dict\n        ctx = context if isinstance(context, StrategyContext) else context_from_dict(context)")
with open("core/movement_registry.py", "w") as f:
    f.write(text)
