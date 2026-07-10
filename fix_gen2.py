import re

with open("scripts/generate_opening_drive_trade_ledger.py", "r") as f:
    c = f.read()

c = c.replace('f_cand.write(json.dumps(cand_base) + "\\\n', 'f_cand.write(json.dumps(cand_base) + "\\n")')

# also check if there's an actual newline
c = re.sub(r'f_cand.write\(json.dumps\(cand_base\) \+ "\n\s*"\)', r'f_cand.write(json.dumps(cand_base) + "\\n")', c)

with open("scripts/generate_opening_drive_trade_ledger.py", "w") as f:
    f.write(c)

