# core/portfolio_manager.py

class PortfolioManager:
    """
    Handles capital allocation, multi-symbol limits, hedging
    """
    def __init__(self, total_capital=100000, symbol_limits=None):
        self.total_capital = total_capital
        self.symbol_limits = symbol_limits or {"NIFTY":0.4,"BANKNIFTY":0.3,"OTHERS":0.3}

    def allocate_capital(self, strategy_scores):
        """
        Allocate capital across strategies and symbols
        """
        allocations = {}
        total_score = sum(max(score,0) for _,score in strategy_scores)
        if total_score == 0:
            for name,_ in strategy_scores:
                allocations[name] = 0
            return allocations
        for name,score in strategy_scores:
            weight = max(score,0)/total_score
            allocations[name] = weight * self.total_capital
        return allocations

    def check_symbol_limit(self, symbol, proposed_amount):
        limit = self.symbol_limits.get(symbol, 0.1) * self.total_capital
        return min(proposed_amount, limit)

    def apply_hedge(self, trade):
        """
        Optional hedge logic: 
        if IV high and CE trade, sell ATM PE partially
        """
        if trade.get("direction")=="UP" and trade.get("iv")>0.25:
            trade["hedge"] = {"type":"PE","quantity":int(trade["quantity"]/2)}
        elif trade.get("direction")=="DOWN" and trade.get("iv")>0.25:
            trade["hedge"] = {"type":"CE","quantity":int(trade["quantity"]/2)}
        else:
            trade["hedge"] = None
        return trade

