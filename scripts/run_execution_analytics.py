from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


from core.execution_analytics import write_execution_analytics

if __name__ == "__main__":
    summary, daily = write_execution_analytics()
    print(summary)
