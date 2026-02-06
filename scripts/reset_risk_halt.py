from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


from core import risk_halt

if __name__ == "__main__":
    payload = risk_halt.clear_halt()
    print(f"Risk halt cleared: {payload}")
