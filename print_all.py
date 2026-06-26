import json

with open("candidate_decisions.jsonl", "r") as f:
    text = f.read()

blocks = text.split("===")
for b in blocks:
    if "{" in b:
        start = b.find("{")
        obj = json.loads(b[start:])
        print(json.dumps(obj, indent=2))
        break
