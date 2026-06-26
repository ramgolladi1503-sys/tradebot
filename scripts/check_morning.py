import json


def run():
    count = 0
    with open(".runtime/logs/ranked_pipeline_runtime_2026-06-23.jsonl", "r") as f:
        for line in f:
            try:
                c = json.loads(line)
                report = c.get("report", {})
                if (
                    report.get("source_candidate_count", 0) > 0
                    or report.get("top_advisory_count", 0) > 0
                    or report.get("top_executable_count", 0) > 0
                ):
                    print(
                        f"Found at {c.get('ts')}: source={report.get('source_candidate_count')} advisory={report.get('top_advisory_count')} executable={report.get('top_executable_count')}"
                    )
                    count += 1
                    if count > 5:
                        break
            except:
                pass
    if count == 0:
        print("No candidates found in ranked_pipeline_runtime_2026-06-23.jsonl")


run()
