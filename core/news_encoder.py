from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from config import config as cfg
from core import news_ingestor


MODEL_PATH = Path(getattr(cfg, "NEWS_CLASSIFIER_PATH", "models/news_shock_model.pkl"))
VEC_PATH = Path(getattr(cfg, "NEWS_VECTOR_PATH", "models/news_vectorizer.pkl"))
OUT_PATH = Path("data/news_shock.json")


KEYWORDS_UP = {"surge", "rally", "beats", "record", "growth", "upgrade"}
KEYWORDS_DOWN = {"crash", "plunge", "miss", "downgrade", "ban", "default", "strike", "fraud"}
KEYWORDS_SHOCK = {"emergency", "policy", "rbi", "cpi", "budget", "rate", "war", "sanctions", "shutdown"}


def _atomic_write(path: Path, payload: dict):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


class NewsEncoder:
    def __init__(self):
        self.model = None
        self.vectorizer = None
        self._load()

    def _load(self):
        try:
            import joblib
            if MODEL_PATH.exists():
                self.model = joblib.load(MODEL_PATH)
            if VEC_PATH.exists():
                self.vectorizer = joblib.load(VEC_PATH)
        except Exception:
            self.model = None
            self.vectorizer = None

    def _heuristic_score(self, title: str) -> float:
        t = title.lower()
        score = 0.0
        if any(k in t for k in KEYWORDS_SHOCK):
            score += 0.6
        if any(k in t for k in KEYWORDS_UP):
            score += 0.2
        if any(k in t for k in KEYWORDS_DOWN):
            score += 0.2
        return min(score, 1.0)

    def _direction_bias(self, title: str) -> float:
        t = title.lower()
        up = any(k in t for k in KEYWORDS_UP)
        dn = any(k in t for k in KEYWORDS_DOWN)
        if up and not dn:
            return 1.0
        if dn and not up:
            return -1.0
        return 0.0

    def encode(self) -> dict:
        headlines = news_ingestor.ingest_headlines()
        if not headlines:
            payload = {
                "shock_score": 0.0,
                "direction_bias": 0.0,
                "uncertainty_index": 0.0,
                "top_headlines": [],
            }
            _atomic_write(OUT_PATH, {"timestamp": datetime.now(timezone.utc).isoformat(), **payload})
            return payload

        decay_min = float(getattr(cfg, "NEWS_SHOCK_DECAY_MINUTES", 180))
        now = datetime.now(timezone.utc)
        scored = []
        for h in headlines:
            title = h.get("title", "")
            ts = h.get("ts")
            try:
                ts_dt = datetime.fromisoformat(ts)
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            except Exception:
                ts_dt = now
            minutes = max((now - ts_dt).total_seconds() / 60.0, 0.0)
            decay = math.exp(-minutes / max(decay_min, 1.0))
            weight = float(h.get("weight", 1.0))
            if self.model is not None and self.vectorizer is not None:
                try:
                    vec = self.vectorizer.transform([title])
                    proba = float(self.model.predict_proba(vec)[0][1])
                except Exception:
                    proba = self._heuristic_score(title)
            else:
                proba = self._heuristic_score(title)
            scored.append({
                "title": title,
                "score": proba * decay * weight,
                "direction": self._direction_bias(title),
                "minutes": minutes,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[: int(getattr(cfg, "NEWS_SHOCK_TOPK", 5))]
        shock_score = float(top[0]["score"]) if top else 0.0
        direction_bias = float(np.mean([t["direction"] for t in top])) if top else 0.0
        uncertainty = 1.0 - min(shock_score, 1.0)

        payload = {
            "shock_score": shock_score,
            "direction_bias": direction_bias,
            "uncertainty_index": uncertainty,
            "top_headlines": top,
        }
        _atomic_write(OUT_PATH, {"timestamp": datetime.now(timezone.utc).isoformat(), **payload})
        return payload
