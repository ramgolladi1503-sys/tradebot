# TradeBot MCP for Antigravity

This package gives Antigravity structured, read-only access to TradeBot research evidence, local market-data audits, machine research gates, and Git scope checks.

It is deliberately **not** a broker, execution, order, merge, reset, delete, credential, or production-configuration interface.

## Components

### `tradebot-evidence`

Reads frozen research context and evidence:

- research status;
- contract and safety boundaries;
- source manifests;
- consumed-evidence and holdout registries;
- candidate fingerprints;
- agent attempts and handoffs;
- artifact SHA-256 verification.

### `tradebot-data-audit`

Performs bounded, read-only inspection of approved Parquet and CSV files:

- schema and row counts;
- session counts;
- timestamp duplicates and order;
- missing intervals;
- bounded session samples;
- backward-only as-of join audits.

It rejects secret-bearing paths, path traversal, symlink escapes, unsupported formats, and files outside configured roots.

### `tradebot-gates`

Evaluates hash-backed evidence manifests. It does not execute arbitrary commands and does not trust narrative phase labels.

Each passing check must include:

- `status: PASS`;
- the producing command;
- `exit_code: 0`;
- a producer commit SHA;
- an artifact path;
- the artifact SHA-256.

Supported gates:

- bootstrap;
- Wave 1 authority;
- temporal integrity;
- candidate freeze;
- walk-forward analysis;
- determinism;
- independent oracle;
- publication.

### `tradebot-git-audit`

Runs only allowlisted read-only Git commands:

- worktree status;
- worktree list;
- ref-to-SHA resolution;
- changed-file lists;
- prohibited-path scanning;
- commit-scope verification;
- cleanliness checks.

There are no write tools for reset, checkout, merge, deletion, force-push, or ref mutation.

## Installation

From the repository root:

```bash
bash scripts/install_antigravity_mcp.sh
```

The installer:

1. creates `.venv-mcp`;
2. installs the stable MCP Python SDK line from `requirements-mcp.txt`;
3. writes the ignored workspace config `.agents/mcp_config.json`;
4. points the four servers at the current repository and evidence roots;
5. performs an import smoke check.

Override roots when needed:

```bash
TRADEBOT_EVIDENCE_ROOT=/Users/madhuram/tradebot-ml-evidence \
TRADEBOT_DATA_ROOTS="/Users/madhuram/tradebot/runtime:/another/read-only/root" \
bash scripts/install_antigravity_mcp.sh
```

Antigravity supports workspace MCP configuration under `.agents/mcp_config.json`. Reload MCP servers from the Antigravity MCP manager after installation.

## Security defaults

Keep MCP tools in **Ask** mode initially. The servers are read-only, but data scans and hashing can still be expensive.

Recommended policy:

- allow evidence reads and Git status tools after review;
- keep large hashing, full session counts, and join audits in Ask mode;
- never add broker or unrestricted shell tools to this package;
- keep non-workspace file access restricted to explicitly configured evidence roots;
- do not place API keys or tokens in MCP configuration.

## Evidence manifest format

`tradebot-gates` expects schema version 1:

```json
{
  "schema_version": 1,
  "gates": {
    "determinism": {
      "checks": {
        "run_a_hash": {
          "status": "PASS",
          "command": "python scripts/run_research.py --out run-a",
          "exit_code": 0,
          "producer_commit": "0123456789abcdef",
          "artifact": "research/evidence/run_a.json",
          "sha256": "64-hex-character-sha256"
        }
      }
    }
  }
}
```

Missing checks, narrative-only claims, non-zero exit codes, unsafe paths, missing producer commits, and hash mismatches return `FAIL`.

## Testing

Core logic uses the repository's existing dependencies:

```bash
pytest -q tests/mcp/test_core.py
```

Server import smoke tests require MCP dependencies:

```bash
python -m pip install -r requirements-mcp.txt
pytest -q -m integration tests/mcp/test_servers.py
```

## What this improves

Antigravity can now ask the project for authoritative state instead of relying on a long chat prompt. More importantly, it cannot truthfully convert a failed machine gate into a successful narrative summary.

This package does not discover an edge by itself. It makes source, temporal, statistical, deterministic, and publication claims harder to fake.
