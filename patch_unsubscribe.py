import re

with open('core/kite_depth_ws.py', 'r') as f:
    content = f.read()

new_content = content.replace(
"""        try:
            if hasattr(ws, "unsubscribe"):
                ws.unsubscribe(to_unsubscribe)
        except Exception as exc:""",
"""        try:
            if hasattr(ws, "unsubscribe"):
                try:
                    from twisted.internet import reactor
                    reactor.callFromThread(ws.unsubscribe, to_unsubscribe)
                except ImportError:
                    ws.unsubscribe(to_unsubscribe)
        except Exception as exc:"""
)

with open('core/kite_depth_ws.py', 'w') as f:
    f.write(new_content)
