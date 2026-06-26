import sys
import json
from pathlib import Path

# Try to read the quote snapshot if it exists
f = Path(".runtime/state/index_quote_snapshot.json")
if f.exists():
    print(f.read_text())
else:
    print("No index_quote_snapshot.json found")
