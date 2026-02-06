class FakeTelegram:
    def __init__(self):
        self.sent = []

    def __call__(self, msg: str):
        self.sent.append(msg)
