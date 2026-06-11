def grep_pattern(filepath, pattern):
    import re
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                print(f"{filepath}:{i+1}: {line.strip()}")

grep_pattern("core/feed_health_truth.py", r"reason_code")
grep_pattern("core/feed_zombie_state.py", r"is_zombie =")
grep_pattern("core/feed_recovery_runtime.py", r"recovery_state=")
grep_pattern("core/feed_runtime.py", r"state =")
