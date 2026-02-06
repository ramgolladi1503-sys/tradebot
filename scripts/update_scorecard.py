from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


from core.scorecard import write_scorecard

if __name__ == "__main__":
    sc = write_scorecard()
    print(sc)
