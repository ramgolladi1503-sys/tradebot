import json

with open("candidate_decisions.jsonl", "r") as f:
    text = f.read()

# file is actually standard output from generate_rca_samples.py which prints JSON blocks separated by titles
blocks = text.split("===")
for b in blocks:
    if "{" in b:
        start = b.find("{")
        obj = json.loads(b[start:])
        if "broker_route_allowed" in obj:
            print("broker_route_allowed:", obj["broker_route_allowed"])
        else:
            print("NO broker_route_allowed")
