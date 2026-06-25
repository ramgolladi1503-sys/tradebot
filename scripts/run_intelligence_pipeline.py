import argparse
import json
import sys
import logging
from typing import Dict, Any

# Assuming path manipulation for standalone execution
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.intelligence.fetchers.http_fetcher import HTTPFetcher
from core.intelligence.extractors.rbi_extractor import RBIExtractor
from core.intelligence.telemetry import MIPTelemetry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_pipeline(dry_run: bool, source_filter: str, max_sources: int, fail_closed: bool) -> Dict[str, Any]:
    telemetry = MIPTelemetry()
    summary = {
        "status": "success",
        "dry_run": dry_run,
        "sources_attempted": 0,
        "events_extracted": 0,
        "failures": []
    }

    # Mocking the source registry for the runner
    sources = [
        {"id": "RBI", "url": "https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx", "extractor": RBIExtractor}
    ]

    if source_filter:
        sources = [s for s in sources if s["id"] == source_filter]

    for s in sources[:max_sources]:
        summary["sources_attempted"] += 1
        telemetry.emit_fetch_event("fetch_started", s["id"], "pending")

        try:
            fetcher = HTTPFetcher(source_id=s["id"])
            payload, status, latency = fetcher.fetch(s["url"])

            if status != "success" or not payload:
                telemetry.emit_fetch_event("fetch_failed", s["id"], status, latency)
                summary["failures"].append({"source": s["id"], "reason": status})
                if fail_closed:
                    summary["status"] = "failed"
                    return summary
                continue

            telemetry.emit_fetch_event("fetch_succeeded", s["id"], "success", latency)

            if not dry_run:
                extractor = s["extractor"](source_domain=s["url"])
                extracted = extractor.safe_extract(payload["raw_content"], s["url"])

                if extracted["status"] == "success":
                    summary["events_extracted"] += 1
                    telemetry.emit_extraction_event("extraction_succeeded", s["id"], "success", extracted["document_hash"])
                else:
                    telemetry.emit_extraction_event("extraction_failed", s["id"], extracted["status"])

        except Exception as e:
            logger.error(f"Pipeline error for {s['id']}: {e}")
            summary["failures"].append({"source": s["id"], "reason": str(e)})
            if fail_closed:
                summary["status"] = "failed"
                return summary

    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MIP Intelligence Runner")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only, do not extract or persist.")
    parser.add_argument("--source", type=str, help="Specific source ID to run (e.g. RBI)")
    parser.add_argument("--max-sources", type=int, default=10, help="Limit number of sources")
    parser.add_argument("--fail-closed", action="store_true", help="Exit 1 immediately on any source failure")

    args = parser.parse_args()

    try:
        result = run_pipeline(args.dry_run, args.source, args.max_sources, args.fail_closed)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "success" else 1)
    except Exception as e:
        logger.error(f"Fatal runner error: {e}")
        sys.exit(1)
