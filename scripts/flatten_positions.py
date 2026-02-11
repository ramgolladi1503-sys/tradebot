from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


from tools.flatten_positions import main


if __name__ == "__main__":
    raise SystemExit(main())
