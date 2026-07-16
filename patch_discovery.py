import re

with open("scripts/run_opening_drive_parameter_discovery.py", "r") as f:
    c = f.read()

# Replace the grid definition
grid_str = """    grid = {
        "opening_drive_window_minutes": [15, 30],
        "min_open_move_points": [20, 40],
        "vwap_alignment_required": [True],
        "stop_atr": [1.0, 1.5],
        "target_rr": [1.5, 2.0],
        "max_trades_per_symbol_day": [2, 3]
    }"""
    
c = re.sub(r'    grid = \{.*?\n    \}', grid_str, c, flags=re.DOTALL)

# Replace the overrides block
override_str = """        overrides = {
            "entry": {
                "opening_drive_window_minutes": combo[0],
                "min_open_move_points": combo[1],
                "vwap_alignment_required": combo[2],
                "max_trades_per_symbol_day": combo[5]
            },
            "stop_loss": {"atr_multiple": combo[3]},
            "target": {"minimum_rr": combo[4]}
        }"""
        
c = re.sub(r'        overrides = \{.*?\n        \}', override_str, c, flags=re.DOTALL)

# Fix the report filename output and conclusions
c = c.replace('OPENING_DRIVE_V1_PARAMETER_SPACE_FAILED', 'OPENING_DRIVE_PARAMETER_SPACE_FAILED')
c = c.replace('OPENING_DRIVE_V1_HOLDOUT_EVALUATED', 'OPENING_DRIVE_HOLDOUT_EVALUATED')
c = c.replace('OPENING_DRIVE_V1_OVERFIT_REGION_FAILED', 'OPENING_DRIVE_OVERFIT_REGION_FAILED')

# Replace the string MRE_V1 inside the conclusion variables, because I used string replacement earlier on MEAN_REVERSION_EXTENSION but the conclusion had MRE
c = c.replace('MRE_V1_', 'OPENING_DRIVE_')

with open("scripts/run_opening_drive_parameter_discovery.py", "w") as f:
    f.write(c)
    
