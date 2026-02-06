import json
import os
import requests
from pathlib import Path
import time
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

OPENAI_API_URL = "https://api.openai.com/v1/responses"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROVIDER = os.getenv("GPT_PROVIDER", "openai").lower()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
TIMEOUT = int(os.getenv("OPENAI_TIMEOUT_SEC", "20"))
MAX_CALLS_PER_MIN = int(os.getenv("GPT_MAX_CALLS_PER_MIN", "10"))
MAX_CALLS_PER_DAY = int(os.getenv("GPT_MAX_CALLS_PER_DAY", "200"))
DAILY_COST_LIMIT = float(os.getenv("GPT_DAILY_COST_LIMIT", "5.0"))
INPUT_COST_PER_1M = float(os.getenv("OPENAI_INPUT_COST_PER_1M", "0.25"))
OUTPUT_COST_PER_1M = float(os.getenv("OPENAI_OUTPUT_COST_PER_1M", "2.0"))
MAX_TOKENS_EST = int(os.getenv("GPT_MAX_TOKENS_EST", "2000"))

USAGE_PATH = Path("logs/gpt_usage.json")


def _schema():
    return {
        "name": "trade_advice",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["buy_now", "wait", "no_trade"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "key_levels": {
                    "type": "object",
                    "properties": {
                        "support": {"type": "number"},
                        "resistance": {"type": "number"},
                        "invalidation": {"type": "number"},
                    },
                    "required": ["support", "resistance", "invalidation"],
                    "additionalProperties": False,
                },
                "rationale": {"type": "string"},
                "risk_notes": {"type": "string"},
            },
            "required": ["action", "confidence", "key_levels", "rationale", "risk_notes"],
            "additionalProperties": False,
        },
    }

def _summary_schema():
    return {
        "name": "day_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "day_type": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "key_levels": {
                    "type": "object",
                    "properties": {
                        "support": {"type": "number"},
                        "resistance": {"type": "number"},
                    },
                    "required": ["support", "resistance"],
                    "additionalProperties": False,
                },
                "plan": {"type": "string"},
                "risk_notes": {"type": "string"},
            },
            "required": ["day_type", "confidence", "key_levels", "plan", "risk_notes"],
            "additionalProperties": False,
        },
    }

def _load_usage():
    if not USAGE_PATH.exists():
        return {"calls": [], "cost": 0.0, "day": ""}
    try:
        return json.loads(USAGE_PATH.read_text())
    except Exception:
        return {"calls": [], "cost": 0.0, "day": ""}

def _save_usage(usage):
    USAGE_PATH.parent.mkdir(exist_ok=True)
    USAGE_PATH.write_text(json.dumps(usage))

def _estimate_cost(input_tokens, output_tokens):
    return (input_tokens / 1_000_000) * INPUT_COST_PER_1M + (output_tokens / 1_000_000) * OUTPUT_COST_PER_1M

def _update_usage_from_response(usage, resp_usage):
    if not resp_usage:
        return
    try:
        in_toks = int(resp_usage.get("input_tokens", resp_usage.get("promptTokenCount", 0)))
        out_toks = int(resp_usage.get("output_tokens", resp_usage.get("candidatesTokenCount", 0)))
    except Exception:
        in_toks = 0
        out_toks = 0
    usage["input_tokens"] = usage.get("input_tokens", 0) + in_toks
    usage["output_tokens"] = usage.get("output_tokens", 0) + out_toks
    usage["cost"] = usage.get("cost", 0.0) + _estimate_cost(in_toks, out_toks)
    _save_usage(usage)

def _can_call():
    usage = _load_usage()
    today = datetime.utcnow().date().isoformat()
    if usage.get("day") != today:
        usage = {"calls": [], "cost": 0.0, "day": today, "input_tokens": 0, "output_tokens": 0}
    now = time.time()
    calls = [t for t in usage.get("calls", []) if now - t <= 60]
    if len(calls) >= MAX_CALLS_PER_MIN:
        return False, "Rate limit: too many GPT calls per minute", usage
    if len(usage.get("calls", [])) >= MAX_CALLS_PER_DAY:
        return False, "Rate limit: daily GPT call cap reached", usage
    if PROVIDER != "gemini":
        est_cost = _estimate_cost(MAX_TOKENS_EST * 0.6, MAX_TOKENS_EST * 0.4)
        if usage.get("cost", 0.0) + est_cost > DAILY_COST_LIMIT:
            return False, "Budget limit: daily GPT cost cap reached", usage
    usage["calls"] = usage.get("calls", [])
    usage["calls"].append(now)
    usage["day"] = today
    _save_usage(usage)
    return True, "", usage


def _extract_text(resp):
    try:
        for item in resp.get("output", []):
            for c in item.get("content", []):
                if "text" in c:
                    return c["text"]
    except Exception:
        return None
    try:
        # Gemini format
        candidates = resp.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and "text" in parts[0]:
                return parts[0]["text"]
    except Exception:
        pass
    try:
        if isinstance(resp, dict) and "output_text" in resp:
            return resp.get("output_text")
    except Exception:
        return None
    return None

def _parse_json_fallback(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try to extract the first JSON object from mixed text
    try:
        import re
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        return None
    return None


def _call_openai(system, user, schema):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set"}
    ok, msg, _ = _can_call()
    if not ok:
        return {"error": msg}
    payload = {
        "model": MODEL,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ],
        "text": {"format": {"type": "json_schema", **schema}},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    r = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=TIMEOUT)
    if r.status_code != 200:
        return {"error": f"OpenAI error {r.status_code}: {r.text}"}
    data = r.json()
    _update_usage_from_response(_load_usage(), data.get("usage"))
    text = _extract_text(data)
    if not text:
        return {"error": "No response text"}
    parsed = _parse_json_fallback(text)
    if parsed is None:
        return {"error": "Invalid JSON response", "raw": text}
    return parsed


def _call_gemini(system, user, schema):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}
    ok, msg, _ = _can_call()
    if not ok:
        return {"error": msg}
    model_name = GEMINI_MODEL.strip()
    if model_name.startswith("models/"):
        model_name = model_name.split("/", 1)[1]
    url = GEMINI_API_URL.format(model=model_name)
    # Gemini doesn't accept JSON schema directly; we enforce via instruction + JSON parsing.
    instruction = (
        system
        + " Return ONLY valid JSON that matches this schema: "
        + json.dumps(schema.get("schema", {}))
    )
    payload = {
        "systemInstruction": {"parts": [{"text": instruction}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(user)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    r = requests.post(f"{url}?key={api_key}", json=payload, timeout=TIMEOUT)
    if r.status_code != 200:
        return {"error": f"Gemini error {r.status_code}: {r.text}"}
    data = r.json()
    _update_usage_from_response(_load_usage(), data.get("usageMetadata"))
    text = _extract_text(data)
    if not text:
        return {"error": "No response text"}
    parsed = _parse_json_fallback(text)
    if parsed is None:
        return {"error": "Invalid JSON response", "raw": text}
    return parsed


def get_trade_advice(trade: dict, market_ctx: dict):
    system = (
        "You are a trading assistant. Provide advisory-only guidance. "
        "Return JSON that matches the provided schema."
    )
    user = {
        "trade": trade,
        "market_context": market_ctx,
        "note": "Advisory only. Do not place orders.",
    }
    if PROVIDER == "gemini":
        return _call_gemini(system, user, _schema())
    return _call_openai(system, user, _schema())

def get_day_summary(market_ctx: dict):
    system = (
        "You are a trading assistant. Provide a high-level day plan. "
        "Return JSON that matches the provided schema."
    )
    user = {
        "market_context": market_ctx,
        "note": "Advisory only.",
    }
    if PROVIDER == "gemini":
        return _call_gemini(system, user, _summary_schema())
    return _call_openai(system, user, _summary_schema())

def test_connection():
    """
    Lightweight connectivity check for configured provider.
    """
    schema = {
        "schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
    }
    system = "Return a JSON object that matches the schema."
    user = {"ping": True}
    if PROVIDER == "gemini":
        return _call_gemini(system, user, schema)
    return _call_openai(system, user, schema)

def list_gemini_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return {"error": f"Gemini error {r.status_code}: {r.text}"}
        data = r.json()
        models = []
        for m in data.get("models", []):
            name = m.get("name")
            methods = m.get("supportedGenerationMethods", [])
            models.append({"name": name, "methods": methods})
        return {"models": models}
    except Exception as e:
        return {"error": str(e)}


def save_advice(trade_id: str, advice: dict, meta: dict | None = None):
    path = Path("logs/gpt_advice.jsonl")
    path.parent.mkdir(exist_ok=True)
    entry = {"trade_id": trade_id, "advice": advice, "meta": meta or {}, "timestamp": datetime.utcnow().isoformat()}
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
