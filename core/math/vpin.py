import numpy as np

def calculate_vpin(tick_volumes, tick_price_changes, bucket_volume):
    """
    Calculates VPIN (Volume-Synchronized Probability of Informed Trading).
    
    VPIN = sum(|V_buy - V_sell|) / (n * bucket_volume)
    
    Args:
        tick_volumes (np.array): Volume of each tick.
        tick_price_changes (np.array): Price change of each tick (used to infer side).
                                       Positive = Buy initiated, Negative = Sell initiated.
        bucket_volume (float): The total volume per volume-synchronized bucket.
        
    Returns:
        float: VPIN score (0.0 to 1.0) indicating order toxicity.
    """
    if len(tick_volumes) == 0 or bucket_volume <= 0:
        return 0.0
        
    v_buy = np.zeros_like(tick_volumes, dtype=float)
    v_sell = np.zeros_like(tick_volumes, dtype=float)
    
    # Simple tick rule: + price change = buyer initiated, - price change = seller initiated
    # Zero price change splits volume 50/50
    for i in range(len(tick_volumes)):
        if tick_price_changes[i] > 0:
            v_buy[i] = tick_volumes[i]
        elif tick_price_changes[i] < 0:
            v_sell[i] = tick_volumes[i]
        else:
            v_buy[i] = tick_volumes[i] / 2.0
            v_sell[i] = tick_volumes[i] / 2.0
            
    # Group into volume buckets
    current_bucket_vol = 0.0
    current_bucket_buy = 0.0
    current_bucket_sell = 0.0
    
    buckets = []
    
    for i in range(len(tick_volumes)):
        vol = tick_volumes[i]
        if vol <= 0:
            continue
            
        # If adding this tick exceeds the bucket volume
        if current_bucket_vol + vol > bucket_volume:
            # Fill the remainder of this bucket
            remainder = bucket_volume - current_bucket_vol
            fraction = remainder / vol
            
            current_bucket_buy += v_buy[i] * fraction
            current_bucket_sell += v_sell[i] * fraction
            
            buckets.append((current_bucket_buy, current_bucket_sell))
            
            # Start new bucket with the leftover
            leftover = vol - remainder
            current_bucket_vol = leftover
            current_bucket_buy = v_buy[i] * (1 - fraction)
            current_bucket_sell = v_sell[i] * (1 - fraction)
        else:
            current_bucket_vol += vol
            current_bucket_buy += v_buy[i]
            current_bucket_sell += v_sell[i]
            
    # If we have buckets, calculate VPIN
    if not buckets:
        # Not enough volume to fill even one bucket, return partial VPIN
        if current_bucket_vol == 0:
            return 0.0
        return abs(current_bucket_buy - current_bucket_sell) / current_bucket_vol
        
    imbalances = [abs(b - s) for b, s in buckets]
    total_volume_in_buckets = len(buckets) * bucket_volume
    
    vpin = sum(imbalances) / total_volume_in_buckets
    return vpin
