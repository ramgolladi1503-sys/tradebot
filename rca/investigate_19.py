def search(filepath, line_nums):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for num in line_nums:
            start = max(0, num - 5)
            end = min(len(lines), num + 5)
            print(f"--- Context for line {num} ---")
            for i in range(start, end):
                print(f"{i+1}: {lines[i].strip()}")

search("core/kite_depth_ws.py", [1521, 1608, 2938, 3196])
