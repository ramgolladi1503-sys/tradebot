def grep_pattern(filepath, pattern):
    import re
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                print(f"{filepath}:{i+1}: {line.strip()}")

grep_pattern("core/kite_depth_ws.py", r"last_ws_tick_age_sec")
grep_pattern("core/kite_depth_ws.py", r"max_age_sec")
