from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


from core.execution_analytics import write_execution_analytics

if __name__ == "__main__":
    try:
        summary, daily = write_execution_analytics()
        print(summary)
    except Exception as exc:
        payload = {
            "status": "degraded",
            "reason_code": "EXECUTION_ANALYTICS_WRITE_FAILED",
            "error": f"{type(exc).__name__}:{exc}",
        }
        print(payload)
