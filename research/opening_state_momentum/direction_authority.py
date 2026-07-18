class DirectionAuthorityError(Exception):
    pass

def normalize_direction(raw_direction) -> str:
    if raw_direction == "LONG" or raw_direction == 1:
        return "LONG"
    elif raw_direction == "SHORT" or raw_direction == -1:
        return "SHORT"
    else:
        raise DirectionAuthorityError(f"Invalid direction: {raw_direction}")
