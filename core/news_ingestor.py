from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

from config import config as cfg


@dataclass
class Headline:
    title: str
    ts: datetime
    source: str
    weight: float
    entities: list


def _source_weight(source: str) -> float:
    weights = getattr(cfg, "NEWS_SOURCE_WEIGHTS", {}) or {}
    return float(weights.get(source, 1.0))


def _extract_entities(title: str) -> list:
    # simple heuristic: capitalized words and acronyms
    tokens = re.findall(r"\b[A-Z][A-Za-z0-9&.\-]{2,}\b", title)
    acronyms = re.findall(r"\b[A-Z]{2,5}\b", title)
    ents = list(dict.fromkeys(tokens + acronyms))
    return ents[:10]


def _parse_rss(xml_text: str, source: str) -> List[Headline]:
    out = []
    if not xml_text:
        return out
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for item in root.findall(".//item"):
        title_el = item.find("title")
        if title_el is None or not title_el.text:
            continue
        title = title_el.text.strip()
        pub_el = item.find("pubDate")
        if pub_el is not None and pub_el.text:
            try:
                ts = parsedate_to_datetime(pub_el.text.strip())
            except Exception:
                ts = datetime.utcnow()
        else:
            ts = datetime.utcnow()
        out.append(
            Headline(
                title=title,
                ts=ts,
                source=source,
                weight=_source_weight(source),
                entities=_extract_entities(title),
            )
        )
    return out


def _default_fetcher(url: str, timeout: int = 10) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def ingest_headlines(
    sources: Optional[Iterable[str]] = None,
    fetcher: Optional[Callable[[str], str]] = None,
) -> List[dict]:
    srcs = list(sources or getattr(cfg, "NEWS_RSS_SOURCES", []) or [])
    if not srcs:
        return []
    fetch = fetcher or _default_fetcher
    seen = set()
    rows: List[Headline] = []

    for url in srcs:
        if not url:
            continue
        try:
            xml_text = fetch(url)
        except Exception:
            continue
        source = urlparse(url).netloc or "rss"
        for h in _parse_rss(xml_text, source):
            key = (h.title.lower().strip(), h.ts.isoformat())
            if key in seen:
                continue
            seen.add(key)
            rows.append(h)

    # Optional API providers (generic JSON list)
    providers = getattr(cfg, "NEWS_API_PROVIDERS", []) or []
    for p in providers:
        try:
            url = p.get("url")
            key = p.get("key")
            source = p.get("name", "api")
            if not url or not key:
                continue
            headers = {"Authorization": f"Bearer {key}"}
            resp = requests.get(url, timeout=10, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            for item in data:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                ts = item.get("ts") or item.get("timestamp")
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    ts = datetime.utcnow()
                h = Headline(
                    title=title,
                    ts=ts,
                    source=source,
                    weight=_source_weight(source),
                    entities=_extract_entities(title),
                )
                key = (h.title.lower().strip(), h.ts.isoformat())
                if key in seen:
                    continue
                seen.add(key)
                rows.append(h)
        except Exception:
            continue

    rows.sort(key=lambda x: x.ts, reverse=True)
    return [
        {
            "title": h.title,
            "ts": h.ts.isoformat(),
            "source": h.source,
            "weight": h.weight,
            "entities": h.entities,
        }
        for h in rows
    ]

