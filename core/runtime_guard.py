import os

EXPECTED = os.path.expanduser("~/tradebot")
cwd = os.path.abspath(os.getcwd())

# allow running from subdirs inside ~/tradebot
if not cwd.startswith(EXPECTED):
    raise RuntimeError(
        f"WRONG REPO ROOT\\n"
        f"Running from: {cwd}\\n"
        f"Expected under: {EXPECTED}\\n"
        f"Fix your terminal working directory / IDE workspace."
    )
