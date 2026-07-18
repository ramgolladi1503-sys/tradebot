import sys
import json
import argparse
import subprocess
import os
import tempfile

def get_git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        return "UNKNOWN"

PLUGIN_CODE = """
import time
import json
import os

results = {}
collected = 0
start_time = 0.0
elapsed = 0.0
exit_code = -1

def pytest_collection_finish(session):
    global collected
    collected = len(session.items)

def pytest_runtest_logreport(report):
    nodeid = report.nodeid
    if nodeid not in results:
        results[nodeid] = {
            "setup": None,
            "call": None,
            "teardown": None
        }
    results[nodeid][report.when] = report

def pytest_sessionstart(session):
    global start_time
    start_time = time.time()
    
def pytest_sessionfinish(session, exitstatus):
    global elapsed, exit_code
    elapsed = time.time() - start_time
    exit_code = exitstatus
    
    passed = 0
    failed = 0
    skipped = 0
    xfailed = 0
    xpassed = 0
    errors = 0
    unclassified = 0
    
    for nodeid, phases in results.items():
        setup = phases.get("setup")
        call = phases.get("call")
        teardown = phases.get("teardown")
        
        if setup and setup.failed:
            errors += 1
        if teardown and teardown.failed:
            errors += 1
            
        classified = False
        
        if setup and setup.skipped:
            skipped += 1
            classified = True
        elif call:
            if call.passed:
                if hasattr(call, "wasxfail"):
                    xpassed += 1
                else:
                    passed += 1
                classified = True
            elif call.failed:
                failed += 1
                classified = True
            elif call.skipped:
                if hasattr(call, "wasxfail"):
                    xfailed += 1
                else:
                    skipped += 1
                classified = True
        
        if not classified:
            unclassified += 1
            
    out_file = os.environ.get("_CAPTURE_PLUGIN_OUT")
    if out_file:
        with open(out_file, "w") as f:
            json.dump({
                "collected": collected,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "xfailed": xfailed,
                "xpassed": xpassed,
                "errors": errors,
                "unclassified": unclassified,
                "elapsed_seconds": round(elapsed, 3),
                "exit_code": int(exit_code)
            }, f)
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=str, help="Path to write JSON report")
    parser.add_argument("target_dir", nargs="?", default="tests/research/opening_state_momentum/")
    args = parser.parse_args()

    target_dir = args.target_dir
    command = ["python", "-m", "pytest", "-q", target_dir]
    
    print(f"Running pytest on {target_dir} in an isolated subprocess...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_path = os.path.join(tmpdir, "pytest_capture_plugin.py")
        with open(plugin_path, "w") as f:
            f.write(PLUGIN_CODE)
            
        metrics_out = os.path.join(tmpdir, "metrics.json")
        
        env = os.environ.copy()
        env["PYTHONPATH"] = tmpdir + (os.pathsep + env["PYTHONPATH"] if "PYTHONPATH" in env else "")
        env["PYTEST_PLUGINS"] = "pytest_capture_plugin"
        env["_CAPTURE_PLUGIN_OUT"] = metrics_out
        
        process = subprocess.run(command, env=env)
        
        if not os.path.exists(metrics_out):
            print("ERROR: Plugin did not produce metrics.", file=sys.stderr)
            sys.exit(1)
            
        with open(metrics_out) as f:
            plugin_data = json.load(f)
            
    collected = plugin_data["collected"]
    passed = plugin_data["passed"]
    failed = plugin_data["failed"]
    skipped = plugin_data["skipped"]
    xfailed = plugin_data["xfailed"]
    xpassed = plugin_data["xpassed"]
    errors = plugin_data["errors"]
    unclassified = plugin_data["unclassified"]
    
    if collected == 0:
        print("ERROR: Zero tests collected.", file=sys.stderr)
        sys.exit(1)
        
    total_terminally_classified = passed + failed + skipped + xfailed + xpassed
    if total_terminally_classified != collected:
        print(f"ERROR: Accounting invariant failed: passed({passed}) + failed({failed}) + skipped({skipped}) + xfailed({xfailed}) + xpassed({xpassed}) = {total_terminally_classified} != collected({collected})", file=sys.stderr)
        print("Errors in setup/teardown prevent some tests from reaching a terminal call phase.", file=sys.stderr)
        print(f"Terminally classified tests: {total_terminally_classified}", file=sys.stderr)
        print(f"Errors: {errors}", file=sys.stderr)
        print(f"Unclassified collected tests: {unclassified}", file=sys.stderr)
        sys.exit(1)
        
    report_data = {
        "command": " ".join(command),
        "git_head": get_git_head(),
        "exit_code": plugin_data["exit_code"],
        "metrics": plugin_data
    }
    
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report_data, f, indent=4)
        print(f"Report written to {args.report}")
    else:
        print(json.dumps(report_data, indent=4))
        
    if plugin_data["exit_code"] != 0:
        print(f"ERROR: Pytest execution returned non-zero exit code {plugin_data['exit_code']}", file=sys.stderr)
        sys.exit(1)
        
    sys.exit(0)

if __name__ == "__main__":
    main()
