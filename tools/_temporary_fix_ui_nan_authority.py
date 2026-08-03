from pathlib import Path

path = Path('dashboard/ui/table_model.py')
text = path.read_text(encoding='utf-8')
old = '''def _stamp_runtime_authority(out: pd.DataFrame) -> pd.DataFrame:\n    if out.empty:\n        return out\n    mode = str(getattr(__import__("config.config", fromlist=["EXECUTION_MODE"]), "EXECUTION_MODE", "SIM") or "SIM")\n    rows = [apply_runtime_authority(row, mode=mode) for row in out.to_dict(orient="records")]\n    stamped = pd.DataFrame(rows, index=out.index)\n'''
new = '''def _authority_record_value(value):\n    """Normalize dataframe missing scalars before authority classification.\n\n    Pandas materializes a column that exists on only some rows with NaN/NaT/\n    pd.NA on the other rows. Numeric NaN is truthy in Python, so passing it to\n    boolean fallback fields can falsely classify a clean row as fallback-driven.\n    Container values are preserved because pd.isna(container) is vectorized.\n    """\n    if isinstance(value, (dict, list, tuple, set)):\n        return value\n    try:\n        if bool(pd.isna(value)):\n            return None\n    except (TypeError, ValueError):\n        pass\n    return value\n\n\ndef _stamp_runtime_authority(out: pd.DataFrame) -> pd.DataFrame:\n    if out.empty:\n        return out\n    mode = str(getattr(__import__("config.config", fromlist=["EXECUTION_MODE"]), "EXECUTION_MODE", "SIM") or "SIM")\n    records = [\n        {key: _authority_record_value(value) for key, value in row.items()}\n        for row in out.to_dict(orient="records")\n    ]\n    rows = [apply_runtime_authority(row, mode=mode) for row in records]\n    stamped = pd.DataFrame(rows, index=out.index)\n'''
count = text.count(old)
if count != 1:
    raise SystemExit(f'UI_AUTHORITY_CONTEXT_COUNT:{count}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('UI missing scalar authority normalization applied')
