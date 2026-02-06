from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


from core import log_lock

if __name__ == "__main__":
    payload = log_lock.unlock()
    print(payload)
