import time

class FakeWebSocket:
    """
    Minimal fake WebSocket for tests.
    Can enqueue messages and simulate disconnects.
    """
    def __init__(self):
        self.connected = False
        self.messages = []
        self.raise_on_recv = False

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def send(self, msg):
        # no-op for tests
        pass

    def recv(self):
        if self.raise_on_recv:
            raise RuntimeError("WebSocket disconnected")
        if not self.messages:
            time.sleep(0.01)
            return None
        return self.messages.pop(0)

    def push(self, msg):
        self.messages.append(msg)
