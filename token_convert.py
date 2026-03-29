# WARNING: Standalone prototype script. Not connected to the live tradebot
# orchestrator, review queue, or execution pipeline. Experimental use only.
from core.kite_client import kite_client

api_key = "yfqy95s55t2noi2n"
api_secret = "7abtdl7h6b722vy7fu7xhzy28a847aea"
request_token = "QCow35Op3VAy7keFo3m3r4uHnEnkCHdh"

data = kite_client.generate_session(request_token, api_secret=api_secret, api_key=api_key)

access_token = data["access_token"]
print(access_token)
