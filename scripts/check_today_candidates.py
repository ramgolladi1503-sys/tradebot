import json


def run():
    count = 0
    with open(".runtime/logs/ranked_pipeline_runtime_2026-06-23.jsonl", "r") as f:
        for line in f:
            try:
                c = json.loads(line)
                report = c.get("report", {})
                if report.get("ranked_candidate_count", 0) > 0:
                    count += report.get("ranked_candidate_count")
            except:
                pass
    print(f"Total candidates ranked today in runtime pipeline: {count}")


run()
