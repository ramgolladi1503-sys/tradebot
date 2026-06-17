from datetime import datetime, timedelta

def get_target_expiry_weekday(date: datetime, ticker: str) -> int:
    """
    Returns the target weekday integer (0-6) for the expiry day 
    based on historical and 2025 standardized rules.
    """
    year = date.year
    month = date.month
    
    # 2025 Standardized Shift
    if year > 2025 or (year == 2025 and month >= 9):
        if "NIFTY" in ticker or "BANKNIFTY" in ticker:
            return 1 # Tuesday for all NSE
        elif "SENSEX" in ticker or "BANKEX" in ticker:
            return 3 # Thursday for all BSE
            
    # Pre-2025 Historical Rules
    if "BANKNIFTY" in ticker:
        if year >= 2023:
            return 2 # Wednesday
        return 3 # Thursday
        
    elif "NIFTY" in ticker:
        return 3 # Thursday historically
        
    elif "SENSEX" in ticker:
        if year >= 2023:
            return 4 # Friday was used briefly, then Thursday. Let's default to Thursday.
        return 3 # Thursday
        
    # Default to Thursday
    return 3

# PRODUCTION UPGRADE: Comprehensive NSE/BSE Floating Holiday Matrix (2024-2026 partial)
# In a truly live system, this reads from an official JSON downloaded from the exchange API weekly.
COMPREHENSIVE_HOLIDAYS = set([
    # 2024
    "2024-01-22", "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29",
    "2024-04-11", "2024-04-17", "2024-05-01", "2024-05-20", "2024-06-17",
    "2024-07-17", "2024-08-15", "2024-10-02", "2024-11-01", "2024-11-15",
    "2024-12-25",
    # 2025 (Projected/Actual depending on lunar)
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-06-06", "2025-08-15",
    "2025-08-27", "2025-10-02", "2025-10-21", "2025-10-22", "2025-11-05",
    "2025-12-25"
])

def is_holiday(date: datetime) -> bool:
    if date.weekday() >= 5: # Weekend
        return True
    
    date_str = date.strftime("%Y-%m-%d")
    return date_str in COMPREHENSIVE_HOLIDAYS

def get_days_to_expiry(current_date: datetime, ticker: str) -> int:
    """
    Calculates exact days to expiry, handling holiday pull-forwards.
    """
    target_weekday = get_target_expiry_weekday(current_date, ticker)
    current_weekday = current_date.weekday()
    
    # Calculate days to the next target weekday
    days_ahead = target_weekday - current_weekday
    if days_ahead < 0: 
        days_ahead += 7
        
    expiry_date = current_date + timedelta(days=days_ahead)
    
    # Holiday Caveat: If expiry is on a holiday, move backward to nearest trading day
    while is_holiday(expiry_date):
        expiry_date -= timedelta(days=1)
        
    # If the shifted expiry date is before the current date, it means we are 
    # looking at the NEXT week's expiry.
    if expiry_date.date() < current_date.date():
        # Jump to next week
        expiry_date = current_date + timedelta(days=days_ahead + 7)
        while is_holiday(expiry_date):
            expiry_date -= timedelta(days=1)
            
    return (expiry_date.date() - current_date.date()).days
