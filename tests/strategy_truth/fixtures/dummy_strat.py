"""
Dummy strategy for truth engine testing.
"""
from core.strategy_registry.strategy_contract import StrategyContract
from datetime import date

# MAGIC_NUMBER literal
THRESHOLD = 42

def execute_order():
    pass

def ranking_hook():
    pass

class DummyStrat:
    """
    Entry rules: MACD crosses signal.
    Exit rules: EMA crosses down.
    Stop logic: 1% stop loss.
    """
    def __init__(self):
        self.RSI = 14
        # TODO: Fix this heuristic
        self.score += 5
        self.probability = 0.8
        
        if self.RSI > 70:
            execute_order()

contract = StrategyContract(
    strategy_id="dummy_strat",
    strategy_name="Dummy Strategy",
    version="1.0",
    owner="test",
    created_date=date(2023, 1, 1),
    description="Test",
    market_hypothesis="Test",
    primary_market="NSE",
    supported_indices=["NIFTY"],
    supported_option_types=["CE"],
    entry_rules_summary="MACD crosses signal",
    exit_rules_summary="EMA crosses down",
    stop_logic_summary="1% stop loss",
    target_logic_summary="2% target",
    time_stop="15:00",
    required_indicators=["RSI", "MACD", "EMA"],
    required_market_data=["NIFTY_SPOT"],
    required_option_data=[],
    required_sessions=[],
    required_liquidity="",
    allowed_regimes=[],
    forbidden_regimes=[],
    required_confirmations=[],
    known_limitations=[],
    known_assumptions=[]
)
