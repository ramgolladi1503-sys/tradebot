from _pytest.monkeypatch import MonkeyPatch
mp = MonkeyPatch()
class C: pass
mp.setattr(C, 'new_attr', True, raising=False)
print(getattr(C, 'new_attr', False))
