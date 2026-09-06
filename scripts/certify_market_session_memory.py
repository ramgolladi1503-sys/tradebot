#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ.setdefault("MARKET_SESSION_MEMORY_DISABLE", "1")

from core.market_session_store import MarketSessionStore, SessionMemoryConflict
from core.market_session_memory_contract import install as install_session_memory_contract
install_session_memory_contract()
from core.ohlc_buffer import OhlcBuffer

IST = ZoneInfo("Asia/Kolkata")


def _bar(ts: datetime, price: float) -> dict:
    return {
        "ts": ts, "open": price, "high": price + 1.0, "low": price - 1.0,
        "close": price + 0.25, "volume": 100.0,
        "bar_provenance": {
            "source_type": "deterministic_test", "live_feed_session_id": "cert-session",
            "replay_fixture": False, "non_live_fallback": False, "recovered_synthetic": False,
        },
    }


def _live_provenance() -> dict:
    return {
        "source_type": "deterministic_test", "live_feed_session_id": "cert-session",
        "replay_fixture": False, "non_live_fallback": False, "recovered_synthetic": False,
    }


def _gate(name: str, fn) -> dict:
    try:
        evidence = fn()
        return {"gate": name, "status": "PASS", "evidence": evidence or {}}
    except Exception as exc:
        return {"gate": name, "status": "FAIL", "error": f"{type(exc).__name__}:{exc}"}


def run_certification(output: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="market_session_memory_cert_") as tmp:
        root = Path(tmp); db_path = root / "session_memory.sqlite"; report_root = root / "reports"
        store = MarketSessionStore(db_path=db_path, report_root=report_root)
        day = datetime(2026, 9, 7, 9, 15, tzinfo=IST)
        for i in range(30):
            store.persist_completed_bar("NIFTY", _bar(day + timedelta(minutes=i), 25000.0 + i))
        gates: list[dict] = []

        def immutable_gate():
            original = _bar(day, 25000.0)
            duplicate = store.persist_completed_bar("NIFTY", original)
            assert duplicate["status"] == "EXISTS"
            mutated = dict(original); mutated["close"] = float(original["close"]) + 10.0; mutated["high"] = float(mutated["close"]) + 1.0
            try:
                store.persist_completed_bar("NIFTY", mutated)
            except SessionMemoryConflict:
                return {"duplicate_status": duplicate["status"], "mutation_rejected": True}
            raise AssertionError("completed-bar mutation was not rejected")
        gates.append(_gate("immutable_completed_bar", immutable_gate))

        def timeframe_gate():
            at_0945 = day + timedelta(minutes=30); at_0944 = day + timedelta(minutes=29)
            one = store.get_bars("NIFTY", as_of=at_0945, timeframe="1m")
            five = store.get_bars("NIFTY", as_of=at_0945, timeframe="5m")
            fifteen = store.get_bars("NIFTY", as_of=at_0945, timeframe="15m")
            fifteen_pre = store.get_bars("NIFTY", as_of=at_0944, timeframe="15m")
            assert len(one) == 30 and len(five) == 6 and len(fifteen) == 2 and len(fifteen_pre) == 1
            return {"1m": len(one), "5m": len(five), "15m": len(fifteen), "15m_before_second_close": len(fifteen_pre)}
        gates.append(_gate("future_safe_timeframe_derivation", timeframe_gate))

        def restart_gate():
            symbol = "FINNIFTY"; writer = OhlcBuffer(session_store=store)
            writer.update_tick(symbol, 21000.0, ts=day, provenance=_live_provenance())
            result = writer.update_tick(symbol, 21001.0, ts=day + timedelta(minutes=1), provenance=_live_provenance())
            assert result.get("session_memory_persisted") is True
            assert len(writer.get_completed_bars(symbol, as_of=day + timedelta(minutes=2))) == 2
            reopened = MarketSessionStore(db_path=db_path, report_root=report_root)
            restarted = OhlcBuffer(session_store=reopened)
            recovered = restarted.get_completed_bars(symbol, as_of=day + timedelta(minutes=2))
            assert len(recovered) == 2 and float(recovered[0]["open"]) == 21000.0
            return {"persist_status": result.get("session_memory_status"), "recovered_bars": len(recovered)}
        gates.append(_gate("restart_read_through", restart_gate))

        def missing_minute_gate():
            symbol = "BANKNIFTY"
            for i in range(10):
                if i != 2: store.persist_completed_bar(symbol, _bar(day + timedelta(minutes=i), 51000.0 + i))
            context = store.build_context(symbol, as_of=day + timedelta(minutes=10))
            five = store.get_bars(symbol, as_of=day + timedelta(minutes=10), timeframe="5m")
            assert context["missing_1m_bars"] == 1 and context["coverage_pct"] == 90.0 and len(five) == 1
            return {"missing": 1, "coverage_pct": 90.0, "derived_5m_bars": len(five)}
        gates.append(_gate("gap_detection_and_derived_bar_rejection", missing_minute_gate))

        def replay_gate():
            symbol = "SENSEX"; buffer = OhlcBuffer(session_store=store)
            replay = {**_live_provenance(), "source_type": "replay_fixture", "replay_fixture": True}
            buffer.update_tick(symbol, 81000.0, ts=day, provenance=replay)
            result = buffer.update_tick(symbol, 81001.0, ts=day + timedelta(minutes=1), provenance=replay)
            durable = store.get_bars(symbol, as_of=day + timedelta(minutes=2), timeframe="1m")
            assert len(durable) == 0 and result.get("session_memory_persisted") is False
            return {"durable_rows": 0, "status": result.get("session_memory_status")}
        gates.append(_gate("replay_isolation", replay_gate))

        def seed_resolution_gate():
            symbol = "MIDCPNIFTY"; buffer = OhlcBuffer(session_store=store); seed = []
            for i in range(5):
                seed.append({"date": day + timedelta(minutes=i * 5), "open": 12000.0+i, "high": 12001.0+i, "low": 11999.0+i, "close": 12000.5+i, "volume": 100})
            assert buffer.seed_bars(symbol, seed).get("accepted") is True
            buffer.get_completed_bars(symbol, as_of=day + timedelta(minutes=30))
            durable = store.get_bars(symbol, as_of=day + timedelta(minutes=30), timeframe="1m")
            assert len(durable) == 0
            return {"five_min_seed_rows": 5, "mislabelled_as_1m": len(durable)}
        gates.append(_gate("historical_seed_resolution_guard", seed_resolution_gate))

        def seal_gate():
            sealed = store.seal_session(day.date().isoformat(), symbols=["NIFTY", "BANKNIFTY", "FINNIFTY"])
            verified = store.verify_seal(day.date().isoformat())
            assert sealed["integrity"]["status"] == "PASS" and verified["status"] == "PASS"
            sha_path = report_root / day.date().isoformat() / "SHA256SUMS.json"; assert sha_path.exists()
            return {"integrity": sealed["integrity"]["status"], "seal_verified": verified["status"], "manifest_hash": sealed.get("manifest_payload_sha256"), "hash_file_exists": True}
        gates.append(_gate("session_seal_integrity", seal_gate))

        result = {
            "certification": "MARKET_SESSION_MEMORY_V1",
            "status": "PASS" if all(g["status"] == "PASS" for g in gates) else "FAIL",
            "gate_count": len(gates), "passed": sum(g["status"] == "PASS" for g in gates),
            "failed": sum(g["status"] != "PASS" for g in gates), "gates": gates,
        }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic certification for Market Session Memory V1")
    parser.add_argument("--output", type=Path, default=Path("evidence/market_session_memory_v1/certification.json"))
    args = parser.parse_args(); result = run_certification(args.output); print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
