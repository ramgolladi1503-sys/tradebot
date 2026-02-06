class FakeTradePredictor:
    def __init__(self, *args, **kwargs):
        pass

    def predict_confidence(self, *_args, **_kwargs):
        return 0.5

    def update_model_online(self, *_args, **_kwargs):
        return None
