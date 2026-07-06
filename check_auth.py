import sys
sys.path.append("/Users/madhuram/tradebot")
from config import config as cfg
print("API_KEY:", cfg.KITE_API_KEY)
print("ACCESS_TOKEN:", cfg.KITE_ACCESS_TOKEN)
