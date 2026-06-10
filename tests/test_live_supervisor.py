import os
import sys
import tempfile
import time
from unittest import mock
import pytest

# Ensure scripts directory is in path to import live_supervisor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
import live_supervisor

def test_supervisor_restarts_on_failure():
    # We will simulate a script that fails 2 times then succeeds.
    script_content = """
import sys
import os

count_file = os.environ["DUMMY_COUNT_FILE"]
try:
    with open(count_file, "r") as f:
        count = int(f.read().strip())
except FileNotFoundError:
    count = 0

count += 1
with open(count_file, "w") as f:
    f.write(str(count))

if count < 3:
    sys.exit(1)
sys.exit(0)
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_script = os.path.join(tmpdir, "dummy_main.py")
        count_file = os.path.join(tmpdir, "count.txt")
        
        with open(dummy_script, "w") as f:
            f.write(script_content)
            
        with mock.patch.dict(os.environ, {
            "LIVE_SUPERVISED_MAX_RESTARTS": "5",
            "LIVE_SUPERVISED_RESTART_WAIT_SEC": "0.1",
            "DUMMY_COUNT_FILE": count_file
        }):
            restarts = live_supervisor.run_supervisor([], executable=sys.executable, script_name=dummy_script)
            
            # Script fails twice, succeeds on the 3rd run.
            # That means it restarted 2 times.
            assert restarts == 2
            
            with open(count_file, "r") as f:
                final_count = int(f.read().strip())
            assert final_count == 3


def test_supervisor_max_restarts_limit():
    # A script that always fails
    script_content = """
import sys
sys.exit(1)
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_script = os.path.join(tmpdir, "dummy_main.py")
        with open(dummy_script, "w") as f:
            f.write(script_content)
            
        with mock.patch.dict(os.environ, {
            "LIVE_SUPERVISED_MAX_RESTARTS": "3",
            "LIVE_SUPERVISED_RESTART_WAIT_SEC": "0.1"
        }):
            restarts = live_supervisor.run_supervisor([], executable=sys.executable, script_name=dummy_script)
            
            # It should hit the max restarts limit
            assert restarts == 3
