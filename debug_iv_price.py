from research.option_analytics_v1.evidence import _model_inputs
from core.option_analytics import PricingModel, OptionType
from dataclasses import replace

for rate in (-0.01, 0.06):
    inputs = _model_inputs(
        model=PricingModel.BLACK_76,
        option_type=OptionType.CALL,
        moneyness=0.9,
        time_days=7.0,
        volatility=0.1,
        rate=rate
    )
    from research.option_analytics_v1.evidence import _oracle_price
    oracle_price = _oracle_price(inputs)
    print(f"Rate: {rate}, Price: {oracle_price}")

