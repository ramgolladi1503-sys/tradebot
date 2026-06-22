from _pytest.monkeypatch import MonkeyPatch
mp = MonkeyPatch()
mp.setattr("config.config.NEW_ATTR", True, raising=False)
import config.config
print(getattr(config.config, 'NEW_ATTR', False))
