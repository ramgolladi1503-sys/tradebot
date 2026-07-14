# TradeBot OpenWiki Evaluation

## Purpose

This integration evaluates OpenWiki as an automatically maintained repository reference for TradeBot.

It is deliberately local-first and review-gated.

OpenWiki-generated pages are **secondary documentation**, not proof that a runtime path is active, safe, production-ready, or validated in live markets.

## Responsibility split

| Layer | Responsibility |
|---|---|
| Source code, tests, runtime artifacts | Technical source of truth |
| OpenWiki | Automatically generated repository navigation and code reference |
| Codex review | Runtime-path verification, contradiction detection, and evidence checking |
| Obsidian | Curated KT, decisions, architecture maps, and interview explanations |

## Safety posture

The evaluation scripts:

- use OpenWiki code mode against the current repository
- use the `openai-chatgpt` provider so a separate metered API key is not required
- require Node.js 20 or newer
- refuse to run on `main` by default
- refuse to run with an already-dirty worktree by default
- do not enable scheduled GitHub Actions
- remove a newly generated OpenWiki workflow after the run so an unreviewed recurring job is not activated
- never place orders or call broker APIs

## First-time setup

Create or switch to an isolated branch or worktree, then run:

```bash
bash scripts/setup_openwiki_local.sh
```

The script will:

1. validate the Git repository and branch
2. validate Node.js and npm
3. install the `openwiki` CLI globally when it is missing
4. start the ChatGPT browser login flow
5. initialize repository documentation under `openwiki/`
6. remove only a workflow file that OpenWiki created during that run
7. print the resulting Git status and review commands

## Updating generated documentation

After code changes:

```bash
bash scripts/update_openwiki_local.sh
```

This updates the existing `openwiki/` documentation with the same TradeBot-specific evidence rules.

## Required review

Before committing generated pages:

```bash
bash scripts/review_openwiki_output.sh
```

Then inspect:

```bash
git diff -- AGENTS.md CLAUDE.md openwiki docs/openwiki scripts/setup_openwiki_local.sh scripts/update_openwiki_local.sh scripts/review_openwiki_output.sh
```

Every important OpenWiki claim must be reviewed against:

- actual startup wiring
- callers and callees
- configuration defaults
- tests that exercise the path
- runtime evidence where available

## Evidence classifications

Generated documentation must use these classifications when runtime status matters:

- `ACTIVE_PRODUCTION`
- `ACTIVE_CONDITIONAL`
- `LEGACY_ACTIVE`
- `LEGACY_INACTIVE`
- `SHADOW`
- `RESEARCH_ONLY`
- `DEPRECATED`
- `DEAD`
- `UNKNOWN`

And these evidence states:

- `PROVEN`
- `PARTIALLY_PROVEN`
- `CLAIMED`
- `UNKNOWN`

## Non-negotiable limitations

OpenWiki must not be treated as sufficient proof of:

- live-market stability
- production readiness
- broker behavior
- execution safety
- strategy edge
- a canonical runtime path when duplicate implementations exist

OpenWiki tells us what the repository appears to contain. The repository, tests, and bounded runtime traces determine what actually runs.
