from core.news_encoder import NewsEncoder
from core import news_ingestor


def test_news_encoder_heuristic(monkeypatch):
    def fake_ingest():
        return [{
            "title": "RBI announces emergency rate hike",
            "ts": "2026-02-05T06:00:00+00:00",
            "source": "example.com",
            "weight": 1.0,
            "entities": ["RBI"],
        }]
    monkeypatch.setattr(news_ingestor, "ingest_headlines", fake_ingest)
    enc = NewsEncoder()
    enc.model = None
    enc.vectorizer = None
    out = enc.encode()
    assert out["shock_score"] > 0
