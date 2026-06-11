def search(filepath, line_nums):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for num in line_nums:
            start = max(0, num - 10)
            end = min(len(lines), num + 10)
            print(f"--- Context for line {num} ---")
            for i in range(start, end):
                print(f"{i+1}: {lines[i].strip()}")

search("core/engine_phase2_adapter.py", [286])
