from autobahn.twisted.websocket import WebSocketClientProtocol
p = WebSocketClientProtocol()
p.state = WebSocketClientProtocol.STATE_CONNECTING
try:
    p.sendMessage(b"test")
except Exception as e:
    print("Exception:", type(e).__name__, e)
