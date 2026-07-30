#!/usr/bin/env python3
"""Build the provider-specific NIFTY 50 live-universe contract.

The script uses the official NSE Indices constituent CSV and a provider-native
broker instrument master. It does not open broker sessions. It writes a stable
contract only when the requested broker provider and token domain align.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.time_utils import IST_TZ

OFFICIAL_NIFTY50_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
PARSER_VERSION = "market_event_graph_live_universe_builder_v2"
PASS_KITE_AUTHORITATIVE_LIVE_UNIVERSE_MAPPING = "PASS_KITE_AUTHORITATIVE_LIVE_UNIVERSE_MAPPING"
PASS_UPSTOX_DOMAIN_MAPPING = "PASS_UPSTOX_DOMAIN_MAPPING"
INVALID_CROSS_BROKER_TOKEN_DOMAIN = "INVALID_CROSS_BROKER_TOKEN_DOMAIN"
BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE = "BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE"
BLOCKED_BY_BROKER_INSTRUMENT_CROSSWALK = "BLOCKED_BY_BROKER_INSTRUMENT_CROSSWALK"
BLOCKED_BY_KITE_INSTRUMENT_MASTER = "BLOCKED_BY_KITE_INSTRUMENT_MASTER"
BROKER_TOKEN_DOMAIN_MISMATCH = "BROKER_TOKEN_DOMAIN_MISMATCH"


@dataclass(frozen=True)
class OfficialConstituent:
    company_name: str
    industry: str
    symbol: str
    series: str
    isin: str


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def retrieve_official_csv(*, local_path: Path | None, output_dir: Path) -> dict[str, Any]:
    retrieved_utc = datetime.now(timezone.utc)
    retrieved_ist = retrieved_utc.astimezone(IST_TZ)
    http_metadata: dict[str, Any] = {}
    if local_path is not None:
        raw = local_path.read_bytes()
        source_url = f"file:{local_path}"
    else:
        request = urllib.request.Request(OFFICIAL_NIFTY50_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            source_url = OFFICIAL_NIFTY50_URL
            http_metadata = {
                "status": getattr(response, "status", None),
                "content_type": response.headers.get("content-type"),
                "last_modified": response.headers.get("last-modified"),
                "etag": response.headers.get("etag"),
            }
    raw_hash = sha256_bytes(raw)
    raw_dir = output_dir / "official_nse"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"ind_nifty50list_{raw_hash[:16]}.csv"
    if not raw_path.exists():
        raw_path.write_bytes(raw)
    return {
        "source_url": source_url,
        "retrieved_at_utc": retrieved_utc.isoformat().replace("+00:00", "Z"),
        "retrieved_at_ist": retrieved_ist.isoformat(),
        "http_metadata": http_metadata,
        "raw_sha256": raw_hash,
        "raw_path": str(raw_path),
        "raw_bytes": raw,
    }


def parse_official_constituents(raw: bytes) -> tuple[list[OfficialConstituent], dict[str, Any]]:
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(text.splitlines()))
    parsed: list[OfficialConstituent] = []
    symbols: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    for row in rows:
        symbol = str(row.get("Symbol") or "").strip().upper()
        series = str(row.get("Series") or "").strip().upper()
        if not symbol or series != "EQ":
            invalid.append(symbol or "<blank>")
            continue
        if symbol in seen:
            duplicates.append(symbol)
            continue
        seen.add(symbol)
        symbols.append(symbol)
        parsed.append(
            OfficialConstituent(
                company_name=str(row.get("Company Name") or "").strip(),
                industry=str(row.get("Industry") or "").strip(),
                symbol=symbol,
                series=series,
                isin=str(row.get("ISIN Code") or "").strip(),
            )
        )
    report = {
        "parser_version": PARSER_VERSION,
        "row_count": len(rows),
        "unique_symbol_count": len(set(symbols)),
        "duplicate_symbols": duplicates,
        "invalid_symbols": invalid,
    }
    if len(parsed) != 50 or duplicates or invalid:
        raise ValueError(f"{BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE}:{report}")
    return parsed, report


def load_broker_instruments(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        raise FileNotFoundError(path)
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    if path.suffixes[-2:] == [".json", ".gz"] or path.suffix == ".json":
        value = json.loads(raw.decode("utf-8"))
        if isinstance(value, Mapping):
            rows = value.get("data") or value.get("instruments") or value.get("rows") or []
        else:
            rows = value
        return [dict(row) for row in rows if isinstance(row, Mapping)], sha256_bytes(raw)
    text = raw.decode("utf-8-sig")
    return [dict(row) for row in csv.DictReader(text.splitlines())], sha256_bytes(raw)


def _field(row: Mapping[str, Any], *names: str) -> str:
    lower = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name in row:
            return str(row.get(name) or "").strip()
        value = lower.get(name.lower())
        if value is not None:
            return str(value).strip()
    return ""


def _token(row: Mapping[str, Any], *, broker_provider: str) -> int | None:
    provider = str(broker_provider).strip().lower()
    if provider == "kite":
        raw = _field(row, "instrument_token", "instrumentToken", "token")
        if not raw:
            return None
        try:
            return int(raw)
        except Exception:
            return None
    raw = _field(row, "instrument_token", "instrumentToken", "token", "instrument_key", "instrumentKey")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _is_nse_cash_equity(row: Mapping[str, Any]) -> bool:
    exchange = _field(row, "exchange", "exchange_segment", "segment")
    instrument_type = _field(row, "instrument_type", "instrumentType", "instrument")
    series = _field(row, "series")
    return exchange.upper() in {"NSE", "NSE_EQ"} and instrument_type.upper() in {"EQ", "EQUITY"} and series.upper() in {"", "EQ"}


def crosswalk_constituents(
    constituents: Iterable[OfficialConstituent],
    instruments: list[dict[str, Any]],
    *,
    broker_provider: str,
    index_symbol: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    used_tokens: set[int] = set()
    for constituent in constituents:
        matches = [
            row for row in instruments
            if _field(row, "tradingsymbol", "trading_symbol", "symbol").upper() == constituent.symbol
            and _is_nse_cash_equity(row)
        ]
        if len(matches) != 1:
            rows.append({
                "official_symbol": constituent.symbol,
                "broker_tradingsymbol": None,
                "exchange": None,
                "series": constituent.series,
                "instrument_type": None,
                "instrument_token": None,
                "mapping_status": "MISSING" if not matches else "AMBIGUOUS",
                "mapping_reason": f"matches={len(matches)}",
            })
            continue
        match = matches[0]
        token = _token(match, broker_provider=broker_provider)
        status = "MAPPED" if token is not None and token not in used_tokens else "DUPLICATE_TOKEN"
        if token is not None:
            used_tokens.add(token)
        rows.append({
            "official_symbol": constituent.symbol,
            "broker_tradingsymbol": _field(match, "tradingsymbol", "trading_symbol", "symbol"),
            "exchange": _field(match, "exchange", "exchange_segment", "segment"),
            "series": _field(match, "series") or constituent.series,
            "instrument_type": _field(match, "instrument_type", "instrumentType", "instrument"),
            "instrument_token": token,
            "mapping_status": status,
            "mapping_reason": "exact_nse_cash_equity_tradingsymbol",
        })
    index_matches = [
        row for row in instruments
        if _field(row, "tradingsymbol", "trading_symbol", "symbol").upper() in {index_symbol.upper(), "NIFTY 50"}
        and _field(row, "exchange", "exchange_segment", "segment").upper() in {"NSE", "NSE_INDEX", "NSE_EQ"}
    ]
    index_mapping = None
    if len(index_matches) == 1 and _token(index_matches[0], broker_provider=broker_provider) is not None:
        row = index_matches[0]
        index_mapping = {
            "symbol": index_symbol.upper(),
            "broker_tradingsymbol": _field(row, "tradingsymbol", "trading_symbol", "symbol"),
            "exchange": _field(row, "exchange", "exchange_segment", "segment"),
            "instrument_type": _field(row, "instrument_type", "instrumentType", "instrument"),
            "instrument_token": _token(row, broker_provider=broker_provider),
            "mapping_status": "MAPPED",
        }
    summary = {
        "official_constituent_count": len(rows),
        "uniquely_mapped_count": sum(row["mapping_status"] == "MAPPED" for row in rows),
        "missing_count": sum(row["mapping_status"] == "MISSING" for row in rows),
        "ambiguous_count": sum(row["mapping_status"] == "AMBIGUOUS" for row in rows),
        "duplicate_token_count": sum(row["mapping_status"] == "DUPLICATE_TOKEN" for row in rows),
        "index_mapping_status": "MAPPED" if index_mapping else "UNMAPPED_OR_AMBIGUOUS",
    }
    return summary, index_mapping, rows


def build_contract(
    *,
    broker_provider: str,
    official: dict[str, Any],
    parse_report: dict[str, Any],
    mapping_summary: dict[str, Any],
    index_mapping: dict[str, Any],
    mapping_rows: list[dict[str, Any]],
    broker_master_path: Path,
    broker_master_sha256: str,
) -> dict[str, Any]:
    token_domain = str(broker_provider).strip().lower()
    stable_payload = {
        "schema_version": 1,
        "broker_provider": token_domain,
        "token_domain": token_domain,
        "name": "NIFTY50_LIVE_UNIVERSE",
        "version": f"{official['raw_sha256'][:16]}_{token_domain}_{broker_master_sha256[:16]}",
        "effective_date": None,
        "source_retrieval_date": official["retrieved_at_utc"][:10],
        "source_page_updated_date": official["http_metadata"].get("last_modified"),
        "official_source_url": official["source_url"],
        "official_raw_sha256": official["raw_sha256"],
        "index_symbol": "NIFTY",
        "index_instrument_token": int(index_mapping["instrument_token"]),
        "constituents": [
            {"symbol": row["official_symbol"], "instrument_token": int(row["instrument_token"])}
            for row in mapping_rows
        ],
        "broker_instrument_master": {
            "path": str(broker_master_path),
            "sha256": broker_master_sha256,
        },
        "provider_native_index_identifier": index_mapping["broker_tradingsymbol"],
    }
    contract = {
        **stable_payload,
        "official_source_provenance": {
            "retrieved_at_utc": official["retrieved_at_utc"],
            "retrieved_at_ist": official["retrieved_at_ist"],
            "http_metadata": official["http_metadata"],
            "raw_path": official["raw_path"],
            "parse_report": parse_report,
        },
        "mapping_summary": mapping_summary,
        "capture_session_id": None,
    }
    contract["canonical_sha256"] = canonical_json_sha256(stable_payload)
    contract["contract_filename"] = (
        f"nifty50_live_universe_{token_domain}_{official['raw_sha256'][:16]}_{broker_master_sha256[:16]}_{contract['canonical_sha256'][:16]}.json"
    )
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-provider", required=True, choices=("kite", "upstox"))
    parser.add_argument("--nse-constituents-csv", type=Path, default=None)
    parser.add_argument("--broker-instruments", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/reference/market_event_graph"))
    parser.add_argument("--index-symbol", default="NIFTY")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    official = retrieve_official_csv(local_path=args.nse_constituents_csv, output_dir=args.output_dir)
    constituents, parse_report = parse_official_constituents(official["raw_bytes"])
    if args.broker_provider == "kite" and not args.broker_instruments.exists():
        report_path = args.output_dir / f"nifty50_live_universe_reconciliation_kite_{official['raw_sha256'][:16]}_missing.json"
        report = {
            "verdict": BLOCKED_BY_KITE_INSTRUMENT_MASTER,
            "broker_provider": "kite",
            "token_domain": "kite",
            "official_source": {key: value for key, value in official.items() if key != "raw_bytes"},
            "parse_report": parse_report,
            "missing_broker_instrument_master": str(args.broker_instruments),
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"verdict": BLOCKED_BY_KITE_INSTRUMENT_MASTER, "report_path": str(report_path)}, sort_keys=True))
        return 2
    instruments, broker_hash = load_broker_instruments(args.broker_instruments)
    mapping_summary, index_mapping, mapping_rows = crosswalk_constituents(
        constituents,
        instruments,
        broker_provider=args.broker_provider,
        index_symbol=args.index_symbol,
    )
    report = {
        "verdict": PASS_KITE_AUTHORITATIVE_LIVE_UNIVERSE_MAPPING if args.broker_provider == "kite" else PASS_UPSTOX_DOMAIN_MAPPING,
        "broker_provider": args.broker_provider,
        "token_domain": args.broker_provider,
        "official_source": {key: value for key, value in official.items() if key != "raw_bytes"},
        "parse_report": parse_report,
        "broker_instrument_master": {"path": str(args.broker_instruments), "sha256": broker_hash},
        "mapping_summary": mapping_summary,
        "index_mapping": index_mapping,
        "mapping_rows": mapping_rows,
    }
    if mapping_summary["uniquely_mapped_count"] != 50 or index_mapping is None:
        report["verdict"] = BLOCKED_BY_BROKER_INSTRUMENT_CROSSWALK
    if args.broker_provider == "kite" and report["verdict"] == PASS_UPSTOX_DOMAIN_MAPPING:
        report["verdict"] = BROKER_TOKEN_DOMAIN_MISMATCH
    report_path = args.output_dir / f"nifty50_live_universe_reconciliation_{args.broker_provider}_{official['raw_sha256'][:16]}_{broker_hash[:16]}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if report["verdict"] not in {PASS_KITE_AUTHORITATIVE_LIVE_UNIVERSE_MAPPING, PASS_UPSTOX_DOMAIN_MAPPING}:
        print(json.dumps({"verdict": report["verdict"], "report_path": str(report_path)}, sort_keys=True))
        return 2
    contract = build_contract(
        broker_provider=args.broker_provider,
        official=official,
        parse_report=parse_report,
        mapping_summary=mapping_summary,
        index_mapping=index_mapping,
        mapping_rows=mapping_rows,
        broker_master_path=args.broker_instruments,
        broker_master_sha256=broker_hash,
    )
    contract_path = args.output_dir / contract["contract_filename"]
    if not contract_path.exists():
        contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "contract_path": str(contract_path), "report_path": str(report_path), "canonical_sha256": contract["canonical_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
