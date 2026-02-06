def confirm_oi_bias(option_chain: list, direction: str) -> bool:
    """
    option_chain: list of dicts with keys:
    strike, call_oi, put_oi, call_oi_change, put_oi_change
    """

    atm = option_chain[len(option_chain) // 2]

    if direction == "CALL":
        return (
            atm["call_oi_change"] > 0 and
            atm["put_oi_change"] < 0
        )

    if direction == "PUT":
        return (
            atm["put_oi_change"] > 0 and
            atm["call_oi_change"] < 0
        )

    return False

