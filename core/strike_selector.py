def select_best_strike(option_chain, bias):
    candidates = []

    for _, row in option_chain.iterrows():
        premium = row["last_price"]
        delta = row["delta"]
        volume = row["volume"]
        oi = row["open_interest"]

        if premium < 70 or premium > 200:
            continue

        if volume < 100_000 or oi < 1_000_000:
            continue

        if bias == "BULLISH" and not (0.35 <= delta <= 0.55):
            continue

        if bias == "BEARISH" and not (-0.55 <= delta <= -0.35):
            continue

        candidates.append(row)

    if not candidates:
        return None

    # Choose highest OI → institutional interest
    return max(candidates, key=lambda x: x["open_interest"])

