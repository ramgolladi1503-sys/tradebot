# Upstox Token Safety Runbook

The currently exposed token must be revoked/regenerated.
Do not use `echo` or inline `export` with token values.
Open `.env` manually with an editor:

```bash
umask 077
nano .env
```

Put only this inside `.env`:

```text
UPSTOX_ACCESS_TOKEN=<fresh-token>
```

Load it silently:

```bash
set -a
. ./.env
set +a
```

Never print token value, prefix, suffix, or length.
