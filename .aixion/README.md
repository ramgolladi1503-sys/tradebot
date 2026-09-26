# TradeBot — Aixion Harness

This directory is the compact operating context for agent-assisted engineering in TradeBot.

It exists to stop every coding session from re-reading the entire repository or relying on chat history.

Use these files in this order:

1. `project.yaml` — stable project metadata, commands, risk boundaries.
2. `context.md` — current operating context and invariants.
3. `task-packet-template.yaml` — bounded execution contract.
4. `decisions.jsonl` — append-only durable decisions.
5. `failures.jsonl` — append-only failed approaches/root causes.
6. `evidence.jsonl` — append-only proof pointers.

Repository `AGENTS.md` remains authoritative for TradeBot agent safety. Nothing in `.aixion/` weakens it.

Rules:
- repository state beats chat memory;
- load only task-relevant files;
- do not inject all research/history by default;
- deterministic checks before model reasoning;
- high-risk runtime paths require explicit human approval;
- never weaken tests, safety gates, or SIM/PAPER/LIVE separation;
- persist durable lessons, not raw transcripts.
