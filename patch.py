import re

with open('core/kite_depth_ws.py', 'r') as f:
    content = f.read()

# We need to wrap ws.subscribe and ws.set_mode in reactor.callFromThread
new_content = content.replace(
"""        if to_subscribe:
            ws.subscribe(to_subscribe)
            ws.set_mode(ws.MODE_FULL, to_subscribe)""",
"""        if to_subscribe:
            try:
                from twisted.internet import reactor
                reactor.callFromThread(ws.subscribe, to_subscribe)
                reactor.callFromThread(ws.set_mode, ws.MODE_FULL, to_subscribe)
            except ImportError:
                ws.subscribe(to_subscribe)
                ws.set_mode(ws.MODE_FULL, to_subscribe)"""
)

new_content = new_content.replace(
"""        try:
            ws.unsubscribe(to_unsubscribe)
        except Exception as exc:""",
"""        try:
            try:
                from twisted.internet import reactor
                reactor.callFromThread(ws.unsubscribe, to_unsubscribe)
            except ImportError:
                ws.unsubscribe(to_unsubscribe)
        except Exception as exc:"""
)

with open('core/kite_depth_ws.py', 'w') as f:
    f.write(new_content)
