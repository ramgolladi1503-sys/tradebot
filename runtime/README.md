# Runtime Directory

This directory is intentionally reserved for local generated output.

Historical market data, replay corpora, broker captures, and generated live evidence must not be committed here. Use the shared data root configured with `TRADEBOT_DATA_ROOT` and the purpose-specific overrides documented in `docs/runtime_data_externalization.md`.
