import json

def run():
    blocked = []
    with open(".runtime/logs/suggestions.jsonl", "r") as f:
        for line in f:
            try:
                c = json.loads(line)
                # print(c.keys())
                if c.get("status_raw") in ["PLANNING", "blocked", "advisory_only", "QUEUE_ONLY"] or c.get("entry_block_reason"):
                    blocked.append(c)
            except:
                pass
                
    print(f"Found {len(blocked)} blocked/planning candidates historically.")
    for c in blocked[-3:]:
        print(f"---")
        print(f"ID: {c.get('advisory_id')}")
        print(f"Entry Block Reason: {c.get('entry_block_reason')}")
        print(f"Final Action: {c.get('decision_trace', {}).get('final_action')}")
        print(f"Expectancy: {c.get('decision_trace', {}).get('expectancy_score')} (Terminal Rank Score: {c.get('terminal_rank_score')})")

run()
