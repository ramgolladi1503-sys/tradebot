from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://in.tradingview.com"
PAGES = tuple(range(1, 43))
UA = "Mozilla/5.0 (compatible; TradeBotResearch/1.0; research-only)"
TIMEOUT = 25
MAX_WORKERS = 4

SCRIPT_RE = re.compile(r"^/script/[A-Za-z0-9]+-[^/?#]+/?$")
TF_RE = re.compile(
    r"\b(?:(\d{1,4})\s*(?:min(?:ute)?s?|m|hour?s?|h)|daily|weekly|monthly)\b",
    re.I,
)

PRIMITIVES: dict[str, tuple[str, ...]] = {
    "EMA": ("ema", "exponential moving average"),
    "SMA": ("sma", "simple moving average"),
    "WMA": ("wma", "weighted moving average"),
    "VWMA": ("vwma", "volume weighted moving average"),
    "VWAP": ("vwap", "volume weighted average price"),
    "RSI": ("rsi", "relative strength index"),
    "MACD": ("macd",),
    "ADX": ("adx", "average directional index"),
    "DMI": ("dmi", "+di", "-di", "directional movement"),
    "ATR": ("atr", "average true range"),
    "BOLLINGER": ("bollinger", "bb ", "bbands"),
    "SUPERTREND": ("supertrend", "super trend"),
    "DONCHIAN": ("donchian",),
    "STOCHASTIC": ("stochastic", "stoch "),
    "CCI": ("cci", "commodity channel index"),
    "WILLIAMS_R": ("williams %r", "williams r"),
    "ROC": ("rate of change", "roc"),
    "MOMENTUM": ("momentum",),
    "ZSCORE": ("z-score", "z score", "zscore", "standard deviation score"),
    "REGRESSION": ("regression", "least squares", "polynomial"),
    "PIVOT": ("pivot", "swing high", "swing low"),
    "OPENING_RANGE": ("opening range", "orb"),
    "PREV_DAY_LEVEL": ("previous day high", "previous day low", "pdh", "pdl"),
    "BREAKOUT": ("breakout", "breakdown", "range break", "channel break"),
    "MEAN_REVERSION": ("mean reversion", "reversion", "fade"),
    "TREND": ("trend following", "trend-following", "trend"),
    "VOLUME": ("volume", "cvd", "volume delta", "obv", "money flow"),
    "ORDER_BLOCK": ("order block", "smc", "smart money"),
    "ICHIMOKU": ("ichimoku",),
    "KELTNER": ("keltner",),
    "PSAR": ("parabolic sar", "psar"),
    "HEIKIN_ASHI": ("heikin ashi",),
    "CANDLE_PATTERN": ("engulfing", "inside bar", "outside bar", "pin bar", "doji", "key reversal"),
}

MARKET_KEYS = (
    "nifty", "bank nifty", "banknifty", "sensex", "finnifty", "index", "indices",
    "xauusd", "gold", "xagusd", "silver", "forex", "crypto", "bitcoin", "btc",
    "stocks", "equities", "futures", "options",
)

EXACT_PHRASES = (
    "buy when", "sell when", "buy signal", "sell signal", "long when", "short when",
    "enter long", "enter short", "entry when", "strategy", "crosses above", "crosses below",
)

INCOMPATIBLE_PHRASES = {
    "OPTIONS_OR_GREEKS": (
        "option chain", "open interest", "oi change", "gamma", "delta exposure", "greeks",
        "implied volatility", "iv percentile", "strike", "call option", "put option",
    ),
    "FUNDAMENTALS": (
        "earnings", "revenue", "balance sheet", "financials", "pe ratio", "p/e ratio",
        "return on equity", "debt to equity", "eps", "fundamental",
    ),
    "EXTERNAL_OR_MULTI_SYMBOL": (
        "intermarket", "relative strength vs", "peer momentum", "sector breadth", "vix",
        "advance decline", "correlation with", "compare with", "dominance",
    ),
    "TRUE_INTRABAR_OR_LOWER_TF": (
        "intrabar", "tick data", "lower timeframe", "1-second", "1 second", "seconds feed",
        "footprint", "bid ask", "bid/ask", "order flow imbalance",
    ),
    "NON_STANDARD_CHART": ("heikin ashi", "renko", "kagi", "point and figure"),
}


@dataclass
class ScriptRecord:
    page: int
    url: str
    script_id: str
    title: str
    author: str | None
    publication_type: str
    visibility: str
    description: str
    primitives: list[str]
    markets: list[str]
    timeframes: list[str]
    incompatibilities: list[str]
    mechanical_score: int
    initial_status: str
    fetch_status: str
    description_sha256: str


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return s


def _get(url: str, *, attempts: int = 3) -> requests.Response:
    last: Exception | None = None
    for i in range(attempts):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=TIMEOUT)
            if r.status_code == 200 and r.text:
                return r
            if r.status_code in {403, 429, 500, 502, 503, 504}:
                time.sleep(1.0 + i * 1.5)
                continue
            r.raise_for_status()
        except Exception as exc:  # pragma: no cover - network path
            last = exc
            time.sleep(1.0 + i * 1.5)
    if last:
        raise last
    raise RuntimeError(f"failed to fetch {url}")


def page_url(page: int) -> str:
    return f"{BASE}/scripts/" if page == 1 else f"{BASE}/scripts/page-{page}/"


def enumerate_page(page: int) -> list[str]:
    html = _get(page_url(page)).text
    soup = BeautifulSoup(html, "html.parser")
    result: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        path = urlparse(href).path if href.startswith("http") else href
        if not SCRIPT_RE.match(path):
            continue
        url = urljoin(BASE, path)
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _compact(text: str, limit: int = 12000) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit]


def _description(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": "description"})
    og = soup.find("meta", attrs={"property": "og:description"})
    candidates = []
    for tag in (meta, og):
        if tag and tag.get("content"):
            candidates.append(str(tag.get("content")))
    body_text = _compact(soup.get_text(" ", strip=True), 20000)
    if candidates:
        desc = max(candidates, key=len)
        if len(desc) >= 80:
            return _compact(desc)
    # Page text is noisier but descriptions are normally server-rendered.
    return body_text


def _title(soup: BeautifulSoup, url: str) -> str:
    h1 = soup.find("h1")
    if h1:
        t = _compact(h1.get_text(" ", strip=True), 300)
        if t:
            return t
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return _compact(str(og.get("content")), 300)
    return url.rstrip("/").split("/")[-1]


def _author(text: str) -> str | None:
    m = re.search(r"\bby\s+([A-Za-z0-9_.-]{2,50})\b", text, re.I)
    return m.group(1) if m else None


def _publication_type(text: str) -> str:
    low = text.lower()
    if "strategy report" in low or re.search(r"\bstrategy\b", low[:1200]):
        return "STRATEGY"
    if "indicator" in low:
        return "INDICATOR"
    if "library" in low:
        return "LIBRARY"
    return "UNKNOWN"


def _visibility(text: str) -> str:
    low = text.lower()
    if "open-source script" in low or "open source script" in low:
        return "OPEN_SOURCE"
    if "invite-only script" in low or "invite only script" in low:
        return "INVITE_ONLY"
    if "protected script" in low:
        return "PROTECTED"
    return "UNKNOWN"


def _primitives(text: str) -> list[str]:
    low = f" {text.lower()} "
    found = []
    for name, keys in PRIMITIVES.items():
        if any(k in low for k in keys):
            found.append(name)
    return sorted(found)


def _markets(text: str) -> list[str]:
    low = text.lower()
    return sorted({k.upper() for k in MARKET_KEYS if k in low})


def _timeframes(text: str) -> list[str]:
    low = text.lower()
    vals: set[str] = set()
    for m in TF_RE.finditer(low):
        vals.add(m.group(0).strip())
    return sorted(vals)


def _incompatibilities(text: str) -> list[str]:
    low = text.lower()
    result = []
    for reason, phrases in INCOMPATIBLE_PHRASES.items():
        if any(p in low for p in phrases):
            result.append(reason)
    return sorted(result)


def _mechanical_score(text: str, primitives: Iterable[str]) -> int:
    low = text.lower()
    score = 0
    score += min(4, sum(1 for p in EXACT_PHRASES if p in low))
    score += min(3, len(list(primitives)))
    score += int(bool(re.search(r"\b(?:\d{1,3})\s*(?:ema|sma|rsi|atr|adx|period|length|bars?)\b", low)))
    score += int("stop loss" in low or "take profit" in low or "target" in low)
    return score


def _status(visibility: str, description: str, primitives: list[str], incompat: list[str], score: int) -> str:
    low = description.lower()
    if incompat:
        return "DATA_INCOMPATIBLE"
    if not primitives:
        return "OPAQUE_OR_NON_SIGNAL"
    if score >= 5 and any(p in low for p in EXACT_PHRASES):
        return "TESTABLE_EXACT_DESCRIPTION_CANDIDATE"
    if score >= 3:
        return "TESTABLE_CANONICAL_MECHANISM"
    if visibility in {"PROTECTED", "INVITE_ONLY"}:
        return "OPAQUE_PROTECTED"
    return "OPAQUE_OR_NON_SIGNAL"


def inspect_script(page: int, url: str) -> ScriptRecord:
    script_id = url.rstrip("/").split("/")[-1].split("-", 1)[0]
    try:
        r = _get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        full = _compact(soup.get_text(" ", strip=True), 30000)
        desc = _description(soup)
        title = _title(soup, url)
        vis = _visibility(full)
        ptype = _publication_type(full)
        prim = _primitives(desc)
        inc = _incompatibilities(desc)
        score = _mechanical_score(desc, prim)
        status = _status(vis, desc, prim, inc, score)
        return ScriptRecord(
            page=page,
            url=url,
            script_id=script_id,
            title=title,
            author=_author(full),
            publication_type=ptype,
            visibility=vis,
            description=desc,
            primitives=prim,
            markets=_markets(desc),
            timeframes=_timeframes(desc),
            incompatibilities=inc,
            mechanical_score=score,
            initial_status=status,
            fetch_status="OK",
            description_sha256=hashlib.sha256(desc.encode("utf-8")).hexdigest(),
        )
    except Exception as exc:  # pragma: no cover - network path
        return ScriptRecord(
            page=page,
            url=url,
            script_id=script_id,
            title=url.rstrip("/").split("/")[-1],
            author=None,
            publication_type="UNKNOWN",
            visibility="UNKNOWN",
            description="",
            primitives=[],
            markets=[],
            timeframes=[],
            incompatibilities=[],
            mechanical_score=0,
            initial_status="FETCH_FAILED",
            fetch_status=f"ERROR:{type(exc).__name__}:{str(exc)[:180]}",
            description_sha256=hashlib.sha256(b"").hexdigest(),
        )


def build_inventory() -> dict[str, Any]:
    page_rows: list[dict[str, Any]] = []
    page_map: dict[str, int] = {}
    enumeration_errors: list[dict[str, Any]] = []
    for page in PAGES:
        try:
            urls = enumerate_page(page)
            page_rows.append({"page": page, "url": page_url(page), "script_count": len(urls)})
            for url in urls:
                page_map.setdefault(url, page)
        except Exception as exc:  # pragma: no cover - network path
            enumeration_errors.append({"page": page, "error": f"{type(exc).__name__}:{exc}"})
            page_rows.append({"page": page, "url": page_url(page), "script_count": 0})

    jobs = sorted(page_map.items(), key=lambda kv: (kv[1], kv[0]))
    records: list[ScriptRecord] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(inspect_script, page, url): (page, url) for url, page in jobs}
        for fut in concurrent.futures.as_completed(futs):
            records.append(fut.result())
    records.sort(key=lambda r: (r.page, r.url))

    status_counts = Counter(r.initial_status for r in records)
    visibility_counts = Counter(r.visibility for r in records)
    type_counts = Counter(r.publication_type for r in records)
    primitive_counts = Counter(p for r in records for p in r.primitives)
    payload: dict[str, Any] = {
        "campaign": "tradingview_public_library_benchmark_v1",
        "source": "https://in.tradingview.com/scripts/",
        "page_range": [1, 42],
        "page_count": len(PAGES),
        "pages": page_rows,
        "enumeration_errors": enumeration_errors,
        "unique_script_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "visibility_counts": dict(sorted(visibility_counts.items())),
        "publication_type_counts": dict(sorted(type_counts.items())),
        "primitive_counts": dict(primitive_counts.most_common()),
        "records": [asdict(r) for r in records],
        "policy": {
            "inventory_frozen_before_benchmark_outcomes": True,
            "all_42_pages_attempted": True,
            "protected_or_invite_source_not_reverse_engineered": True,
            "description_only_rules_must_be_mechanically_reproducible": True,
            "unopened_tail_accessed": False,
            "same_corpus_structural_edge_certification_authorized": False,
        },
    }
    payload["semantic_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return payload


def write_inventory(output: Path) -> dict[str, Any]:
    payload = build_inventory()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
