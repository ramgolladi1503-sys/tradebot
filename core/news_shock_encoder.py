from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from config import config as cfg


def _load_jsonl(path: str) -> List[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _ts_parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def _decay(dt_hours: float, half_life: float) -> float:
    if dt_hours <= 0:
        return 1.0
    return math.exp(-math.log(2) * dt_hours / max(half_life, 1e-6))


def _sentiment(text: str) -> float:
    if not text:
        return 0.0
    t = text.lower()
    pos = ["beat", "surge", "strong", "up", "positive", "rally", "hawkish"]
    neg = ["miss", "weak", "down", "negative", "selloff", "crash", "dovish", "panic"]
    score = 0
    for w in pos:
        if w in t:
            score += 1
    for w in neg:
        if w in t:
            score -= 1
    if score == 0:
        return 0.0
    return max(-1.0, min(1.0, score / 4.0))


def _keyword_magnitude(text: str) -> float:
    t = (text or "").lower()
    base = 0.15
    if any(k in t for k in ["cpi", "inflation", "rbi", "fed", "rate", "budget", "gdp", "jobs", "fomc"]):
        base += 0.35
    if any(k in t for k in ["surprise", "emergency", "shock", "crisis", "panic"]):
        base += 0.35
    if any(k in t for k in ["earnings", "results", "guidance"]):
        base += 0.15
    return min(1.0, base)


class NewsShockEncoder:
    """
    Encodes events + headlines into a shock score and bias.
    Uses transformer embeddings if available; otherwise keyword heuristics.
    """
    def __init__(self):
        self.half_life = float(getattr(cfg, "NEWS_HALF_LIFE_HOURS", 6.0))
        self._embedder = None
        self._load_embedder()

    def _load_embedder(self):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            self._embedder = None

    def encode(self, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        events = _load_jsonl("logs/economic_calendar.jsonl")
        earnings = _load_jsonl("logs/earnings_calendar.jsonl")
        headlines = _load_jsonl("logs/news_headlines.jsonl")

        shock = 0.0
        macro_bias = 0.0
        uncertainty = 0.0

        def process(items, weight=1.0):
            nonlocal shock, macro_bias, uncertainty
            for it in items:
                ts = _ts_parse(it.get("timestamp") or it.get("time"))
                if not ts:
                    continue
                dt = abs((now - ts).total_seconds()) / 3600.0
                decay = _decay(dt, self.half_life)
                text = it.get("headline") or it.get("event") or it.get("title") or ""
                mag = _keyword_magnitude(text) * weight
                shock = max(shock, mag * decay)
                s = _sentiment(text)
                macro_bias += s * decay * weight
                uncertainty += (1 - abs(s)) * decay * weight

        process(events, weight=1.0)
        process(earnings, weight=0.7)
        process(headlines, weight=0.8)

        shock = max(0.0, min(1.0, shock))
        macro_bias = max(-1.0, min(1.0, macro_bias))
        uncertainty = max(0.0, min(1.0, uncertainty))

        return {
            "shock_score": shock,
            "macro_direction_bias": macro_bias,
            "uncertainty_index": uncertainty,
        }
