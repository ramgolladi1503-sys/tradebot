import os
import sys
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Disable heavy ML in test-only harness
os.environ.setdefault("DISABLE_ML", "true")

# Provide lightweight stubs if optional ML deps are missing (keeps CI green)
try:
    import xgboost  # noqa: F401
except Exception:
    xgb_stub = types.ModuleType("xgboost")
    class _XGBClassifier:
        def __init__(self, *a, **k):
            pass
        def predict(self, X):
            return []
        def predict_proba(self, X):
            return [[0.5, 0.5]]
        def fit(self, *a, **k):
            return self
    xgb_stub.XGBClassifier = _XGBClassifier
    sys.modules["xgboost"] = xgb_stub

try:
    import sklearn  # noqa: F401
except Exception:
    skl_stub = types.ModuleType("sklearn")
    ms_stub = types.ModuleType("sklearn.model_selection")
    metrics_stub = types.ModuleType("sklearn.metrics")
    def _train_test_split(*a, **k):
        return a
    def _accuracy_score(*a, **k):
        return 0.0
    ms_stub.train_test_split = _train_test_split
    metrics_stub.accuracy_score = _accuracy_score
    sys.modules["sklearn"] = skl_stub
    sys.modules["sklearn.model_selection"] = ms_stub
    sys.modules["sklearn.metrics"] = metrics_stub

try:
    import joblib  # noqa: F401
except Exception:
    joblib_stub = types.ModuleType("joblib")
    def _load(*a, **k):
        return {}
    def _dump(*a, **k):
        return None
    joblib_stub.load = _load
    joblib_stub.dump = _dump
    sys.modules["joblib"] = joblib_stub

# Patch Orchestrator to use a fake predictor (avoids loading XGBoost model)
try:
    import core.orchestrator as orch_mod
    from testing.mocks.fake_predictor import FakeTradePredictor
    orch_mod.TradePredictor = FakeTradePredictor
except Exception:
    pass

# Common fixtures
import pytest
from testing.mocks.fake_kite import FakeKiteClient
from testing.mocks.fake_telegram import FakeTelegram
from testing.mocks.fake_market_data import FakeMarketFetcher
from testing.mocks.fake_websocket import FakeWebSocket

@pytest.fixture
def fake_kite():
    return FakeKiteClient()

@pytest.fixture
def fake_telegram():
    return FakeTelegram()

@pytest.fixture
def fake_market_data():
    return FakeMarketFetcher([])

@pytest.fixture
def fake_ws():
    return FakeWebSocket()
