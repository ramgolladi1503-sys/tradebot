# Runtime Baseline

## Python version

- Required runtime: **Python 3.12**
- Local hint file: `.python-version`

## Reproducible dependency install

Install pinned dependencies:

```bash
make setup
```

Equivalent command:

```bash
python3.12 -m pip install -r requirements.lock
```

## Standard commands

Run deterministic test gate:

```bash
make test
```

Run paper mode:

```bash
make run-paper
```

Run live mode (fail-closed gates still apply):

```bash
make run-live
```

Run full sanity script:

```bash
make sanity
```
