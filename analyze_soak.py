import json
import os
from collections import Counter

dir_path = "/Users/madhuram/.gemini/antigravity/brain/a9d80830-a851-4aa0-959f-699d7a8f9d24/soak_telemetry"

decisions_path = os.path.join(dir_path, "decisions.jsonl")
incidents_path = os.path.join(dir_path, "incidents.jsonl")
rejects_path = os.path.join(dir_path, "reject_reasons.jsonl")

decisions = []
if os.path.exists(decisions_path):
    with open(decisions_path, 'r') as f:
        for line in f:
            if line.strip(): decisions.append(json.loads(line))

incidents = []
if os.path.exists(incidents_path):
    with open(incidents_path, 'r') as f:
        for line in f:
            if line.strip(): incidents.append(json.loads(line))

rejects = []
if os.path.exists(rejects_path):
    with open(rejects_path, 'r') as f:
        for line in f:
            if line.strip(): rejects.append(json.loads(line))

print("=== DECISIONS ===")
print(f"Total Decisions: {len(decisions)}")
allowed = [d for d in decisions if d.get('allowed')]
print(f"Allowed Decisions: {len(allowed)}")

# Analyze confidences and strategies for allowed
if allowed:
    print("\nStrategies for allowed:")
    print(Counter(d.get('gate_family') for d in allowed).most_common())
    
    print("\nSymbols for allowed:")
    print(Counter(d.get('symbol') for d in allowed).most_common())
    
    print("\nAverage confidence by gate family:")
    family_conf = {}
    for d in allowed:
        family = d.get('gate_family')
        conf = d.get('confidence', 0)
        family_conf.setdefault(family, []).append(conf)
    for f, confs in family_conf.items():
        print(f"  {f}: {sum(confs)/len(confs):.4f} (count: {len(confs)})")

print("\n=== REJECTS ===")
print(f"Total Rejects: {len(rejects)}")
print("\nTop Reject Reasons:")
print(Counter(r.get('reason_code') or r.get('reason') for r in rejects).most_common(10))

print("\n=== INCIDENTS ===")
print(f"Total Incidents: {len(incidents)}")
if incidents:
    print("\nIncident Types:")
    print(Counter(i.get('incident_type') or i.get('error_type') for i in incidents).most_common(10))
