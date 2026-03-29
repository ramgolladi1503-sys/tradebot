from pathlib import Path


def _load_env_example():
    env_path = Path(__file__).resolve().parents[1] / ".env.example"
    values = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_env_example_keeps_live_quote_requirements_consistent():
    values = _load_env_example()

    assert values["REQUIRE_LIVE_OPTION_QUOTES"] == "true"
    assert values["FORCE_SYNTH_CHAIN_ON_FAIL"] == "false"
    assert values["ALLOW_STALE_LTP"] == "false"
    assert values["ALLOW_CLOSE_FALLBACK"] == "false"


def test_env_example_uses_short_ltp_cache_ttl_when_stale_quotes_are_disabled():
    values = _load_env_example()

    assert values["LTP_CACHE_TTL_SEC"] == "60"
