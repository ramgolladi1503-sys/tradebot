#!/usr/bin/env python3
"""Build a synchronized causal BANKNIFTY/NIFTY/SENSEX research matrix.

Uses exact timestamp intersection only. Features at timestamp t use information
available at or before t. No future rows are referenced. Research-only: never
certifies edge or grants runtime/broker authority.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math
from pathlib import Path
from typing import Any


def f(r: dict[str, Any], k: str, d: float = 0.0) -> float:
    try: return float(r.get(k, d) or d)
    except (TypeError, ValueError): return d


def read(path: Path, instrument: str) -> dict[str, dict[str, Any]]:
    out = {}
    with path.open(newline="", encoding="utf-8") as h:
        for r in csv.DictReader(h):
            if str(r.get("instrument", "")).upper() != instrument.upper():
                continue
            ts = str(r.get("timestamp", ""))
            if ts:
                out[ts] = r
    return out


def ret_bps(a: float, b: float) -> float:
    return 0.0 if a <= 0 else (b-a)/a*10000.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(bank: Path, nifty: Path, sensex: Path, output: Path) -> dict[str, Any]:
    b = read(bank, "BANKNIFTY"); n = read(nifty, "NIFTY"); s = read(sensex, "SENSEX")
    common = sorted(set(b) & set(n) & set(s))
    rows = []
    prev = {"BANKNIFTY": None, "NIFTY": None, "SENSEX": None}
    prev_session = None
    session_open = {}
    for ts in common:
        day = ts[:10]
        if day != prev_session:
            session_open = {
                "BANKNIFTY": f(b[ts], "open", f(b[ts], "close")),
                "NIFTY": f(n[ts], "open", f(n[ts], "close")),
                "SENSEX": f(s[ts], "open", f(s[ts], "close")),
            }
            prev = {"BANKNIFTY": None, "NIFTY": None, "SENSEX": None}
            prev_session = day
        bc, nc, sc = f(b[ts], "close"), f(n[ts], "close"), f(s[ts], "close")
        br = 0.0 if prev["BANKNIFTY"] is None else ret_bps(prev["BANKNIFTY"], bc)
        nr = 0.0 if prev["NIFTY"] is None else ret_bps(prev["NIFTY"], nc)
        sr = 0.0 if prev["SENSEX"] is None else ret_bps(prev["SENSEX"], sc)
        brow = {
            "timestamp": ts,
            "session": day,
            "banknifty_open": f(b[ts], "open"), "banknifty_high": f(b[ts], "high"), "banknifty_low": f(b[ts], "low"), "banknifty_close": bc,
            "nifty_close": nc, "sensex_close": sc,
            "banknifty_ret_1_bps": br, "nifty_ret_1_bps": nr, "sensex_ret_1_bps": sr,
            "banknifty_from_open_bps": ret_bps(session_open["BANKNIFTY"], bc),
            "nifty_from_open_bps": ret_bps(session_open["NIFTY"], nc),
            "sensex_from_open_bps": ret_bps(session_open["SENSEX"], sc),
            "bn_minus_nifty_bps": br - nr,
            "bn_minus_sensex_bps": br - sr,
            "leaders_consensus": (1 if nr > 0 else -1 if nr < 0 else 0) + (1 if sr > 0 else -1 if sr < 0 else 0),
            "certification": "NOT_CERTIFIED", "runtime_authority": "NONE", "broker_actions_allowed": False,
        }
        rows.append(brow)
        prev = {"BANKNIFTY": bc, "NIFTY": nc, "SENSEX": sc}
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with output.open("w", newline="", encoding="utf-8") as h:
        if rows:
            w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)
    sessions = sorted({r["session"] for r in rows})
    manifest = {
        "schema_version": "tradebot-cross-market-matrix-v1",
        "status": "PASS" if rows else "EMPTY",
        "rows": len(rows), "sessions": len(sessions), "first_session": sessions[0] if sessions else None, "last_session": sessions[-1] if sessions else None,
        "input_sha256": {"BANKNIFTY": sha256(bank), "NIFTY": sha256(nifty), "SENSEX": sha256(sensex)},
        "output": str(output.resolve()), "output_sha256": sha256(output) if rows else None,
        "timestamp_join": "EXACT_INTERSECTION", "feature_timing": "CURRENT_OR_PRIOR_ONLY",
        "certification": "NOT_CERTIFIED", "runtime_authority": "NONE", "broker_actions_allowed": False,
    }
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banknifty", required=True); p.add_argument("--nifty", required=True); p.add_argument("--sensex", required=True); p.add_argument("--output", required=True); p.add_argument("--manifest", required=True)
    a = p.parse_args(argv)
    result = build(Path(a.banknifty), Path(a.nifty), Path(a.sensex), Path(a.output))
    Path(a.manifest).parent.mkdir(parents=True, exist_ok=True)
    Path(a.manifest).write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2)); return 0 if result["status"] == "PASS" else 2

if __name__ == "__main__": raise SystemExit(main())
