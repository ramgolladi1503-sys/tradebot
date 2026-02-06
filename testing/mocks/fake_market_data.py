class FakeMarketFetcher:
    def __init__(self, payload):
        self.payload = payload

    def __call__(self, *args, **kwargs):
        return self.payload
