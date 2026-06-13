from core.kite_depth_ws import get_kite_ticker
ticker = get_kite_ticker(api_key="mock", access_token="mock", debug=True)
def on_connect(ws, response):
    print("ON CONNECT FIRED")
def on_open(ws):
    print("ON OPEN FIRED")
ticker.on_connect = on_connect
ticker.on_open = on_open
print("Connecting...")
try:
    ticker.connect()
except Exception as e:
    print("Error:", e)
