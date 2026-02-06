from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

if __name__ == "__main__":
    provider = os.getenv("GPT_PROVIDER", "openai").lower()
    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            print("GEMINI_API_KEY: MISSING")
        else:
            print(f"GEMINI_API_KEY: SET (length {len(key)})")
    else:
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            print("OPENAI_API_KEY: MISSING")
        else:
            print(f"OPENAI_API_KEY: SET (length {len(key)})")
