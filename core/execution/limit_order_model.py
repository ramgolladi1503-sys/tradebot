import logging

logger = logging.getLogger(__name__)

def predict_queue_execution_prob(bid_volume, ask_volume, order_side, queue_position=None):
    """
    Predicts the probability of a passive limit order being filled based on L2 imbalance.
    
    Args:
        bid_volume (float): Total resting volume on the bid.
        ask_volume (float): Total resting volume on the ask.
        order_side (str): 'BUY' or 'SELL'.
        queue_position (float): Optional estimated position in the queue.
        
    Returns:
        float: Probability (0.0 to 1.0) of execution.
    """
    try:
        total_volume = bid_volume + ask_volume
        if total_volume <= 0:
            return 0.5
            
        # Imbalance = (Bid - Ask) / (Bid + Ask)
        # +1.0 = All bids, -1.0 = All asks
        imbalance = (bid_volume - ask_volume) / total_volume
        
        if order_side.upper() == 'BUY':
            # If we are buying (placing a bid limit order), we want sellers to hit us.
            # If imbalance is deeply positive (huge bids, few asks), price will probably go up without us getting filled.
            # If imbalance is negative (huge asks, few bids), we will likely get filled as sellers hit the bid.
            base_prob = 0.5 - (imbalance * 0.4)
        else:
            # If we are selling (placing an ask limit order), we want buyers to hit us.
            # If imbalance is positive (huge bids), buyers will likely hit our ask.
            base_prob = 0.5 + (imbalance * 0.4)
            
        # If queue position is known, adjust probability
        if queue_position is not None and queue_position > 0:
            # The further back in the queue, the lower the probability
            base_prob = base_prob * (1.0 / (1.0 + (queue_position / 1000.0)))
            
        return max(0.01, min(0.99, base_prob))
    except Exception as e:
        logger.error(f"Queue prediction failed: {e}")
        return 0.5

def validate_component_order_flow(index_symbol, index_trade_side, components_l2_data, min_support_ratio=0.3):
    """
    Validates an index breakout trade by checking the L2 data of its heaviest components.
    e.g., BankNifty breakout requires HDFC/ICICI not to have massive opposing walls.
    
    Args:
        index_symbol (str): e.g., 'BANKNIFTY'
        index_trade_side (str): 'BUY' or 'SELL'
        components_l2_data (dict): Mapping of component symbol to L2 data dict.
        min_support_ratio (float): The minimum ratio of supportive imbalance required.
        
    Returns:
        bool: True if order flow supports the index trade, False to veto.
    """
    if not components_l2_data:
        # Fail open if component data is missing so we don't break the system
        return True
        
    try:
        supportive_weight = 0.0
        total_weight = 0.0
        
        for symbol, l2 in components_l2_data.items():
            # Assume equal weighting for this generic function, or pass weight in l2 dict
            weight = l2.get('weight', 1.0)
            total_weight += weight
            
            bid_vol = l2.get('bid_volume', 0)
            ask_vol = l2.get('ask_volume', 0)
            total_vol = bid_vol + ask_vol
            
            if total_vol <= 0:
                continue
                
            imbalance = (bid_vol - ask_vol) / total_vol
            
            if index_trade_side.upper() == 'BUY':
                # We want positive imbalance (more bids than asks) to support a breakout
                # If imbalance is massively negative (e.g. -0.8), it fails this check
                if imbalance > -0.3: 
                    supportive_weight += weight
            else:
                # We want negative imbalance (more asks than bids) to support a breakdown
                if imbalance < 0.3:
                    supportive_weight += weight
                    
        if total_weight <= 0:
            return True
            
        support_ratio = supportive_weight / total_weight
        return support_ratio >= min_support_ratio
        
    except Exception as e:
        logger.error(f"Component validation failed: {e}")
        return True
