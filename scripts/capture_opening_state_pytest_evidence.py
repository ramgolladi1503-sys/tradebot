import sys
import json
import argparse
import subprocess
import pytest
import time
from pathlib import Path

class MetricsCapturePlugin:
    def __init__(self):
        self.collected = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.xfailed = 0
        self.xpassed = 0
        self.deselected = 0
        self.errors = 0
        self.start_time = 0.0
        self.elapsed = 0.0
        self.exit_code = -1
    
    def pytest_collection_finish(self, session):
        self.collected = len(session.items)
    
    def pytest_runtest_logreport(self, report):
        if report.when == "setup":
            if report.failed:
                self.errors += 1
            elif report.skipped:
                self.skipped += 1
        elif report.when == "call":
            if report.passed:
                self.passed += 1
            elif report.failed:
                if hasattr(report, "wasxfail"):
                    self.xpassed += 1
                else:
                    self.failed += 1
            elif report.skipped:
                if hasattr(report, "wasxfail"):
                    self.xfailed += 1
                else:
                    self.skipped += 1
        elif report.when == "teardown":
            if report.failed:
                self.errors += 1
    
    def pytest_deselected(self, items):
        self.deselected += len(items)

    def pytest_sessionstart(self, session):
        self.start_time = time.time()
        
    def pytest_sessionfinish(self, session, exitstatus):
        self.elapsed = time.time() - self.start_time
        self.exit_code = exitstatus

def get_git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except subprocess.CalledProcessError:
        return "UNKNOWN"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=str, help="Path to write JSON report")
    args = parser.parse_args()

    plugin = MetricsCapturePlugin()
    target_dir = "tests/research/opening_state_momentum/"
    command = ["pytest", "-q", target_dir]
    
    print(f"Running pytest on {target_dir}...")
    
    # Run pytest in process to capture metrics natively
    exit_code = pytest.main(["-q", target_dir], plugins=[plugin])
    
    if plugin.collected == 0:
        print("ERROR: Zero tests collected.")
        sys.exit(1)
        
    if plugin.passed > plugin.collected:
        print("ERROR: Passed count exceeds collected count.")
        sys.exit(1)
        
    total_run = plugin.passed + plugin.failed + plugin.skipped + plugin.xfailed + plugin.xpassed + plugin.errors
    if total_run > plugin.collected:
        print(f"ERROR: Accounting mismatch: {total_run} outcomes vs {plugin.collected} collected.")
        sys.exit(1)
        
    report_data = {
        "command": " ".join(command),
        "git_head": get_git_head(),
        "exit_code": int(exit_code),
        "metrics": {
            "collected": plugin.collected,
            "passed": plugin.passed,
            "failed": plugin.failed,
            "skipped": plugin.skipped,
            "xfailed": plugin.xfailed,
            "xpassed": plugin.xpassed,
            "errors": plugin.errors,
            "deselected": plugin.deselected,
            "elapsed_seconds": round(plugin.elapsed, 3)
        }
    }
    
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report_data, f, indent=4)
        print(f"Report written to {args.report}")
    else:
        print(json.dumps(report_data, indent=4))
        
    if exit_code != 0:
        print(f"ERROR: Pytest execution returned non-zero exit code {exit_code}")
        sys.exit(1)
        
    sys.exit(0)

if __name__ == "__main__":
    main()
