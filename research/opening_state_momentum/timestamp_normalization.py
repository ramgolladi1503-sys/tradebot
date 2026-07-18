import pandas as pd

def normalize_timestamps(ts_series: pd.Series) -> pd.Series:
    """
    Normalizes a timestamp series to Asia/Kolkata.
    - If naive, localizes to Asia/Kolkata (does not assume UTC).
    - If aware, converts to Asia/Kolkata.
    - Rejects mixed aware/naive, unparsable, and duplicates.
    """
    if len(ts_series) == 0:
        return pd.Series(dtype="datetime64[ns, Asia/Kolkata]")
        
    try:
        # If the input has mixed timezones, pd.to_datetime either raises or creates an object array.
        # We pass utc=False to avoid automatic conversion to UTC if they are mixed or naive.
        parsed = pd.to_datetime(ts_series)
    except Exception as e:
        raise ValueError(f"Unparsable timestamps: {e}")
        
    if parsed.isna().any():
        raise ValueError("Unparsable timestamps resulted in NaT.")
        
    if parsed.dtype == 'O':
        # If it returned object dtype, it usually means mixed timezones or unparsable types.
        raise ValueError("Mixed aware/naive values or ambiguous schema.")
        
    if parsed.dt.tz is None:
        try:
            normalized = parsed.dt.tz_localize("Asia/Kolkata", ambiguous='raise', nonexistent='raise')
        except Exception as e:
            raise ValueError(f"Ambiguous schema during localization: {e}")
    else:
        normalized = parsed.dt.tz_convert("Asia/Kolkata")
        
    if normalized.duplicated().any():
        raise ValueError("Duplicate normalized timestamps.")
        
    return normalized
