# Hypothesis Annotation System — Design

Date: 2026-07-15 · Status: implemented (autonomous session; decisions documented here for review)

## Goal

1. Pull every Hypothesis annotation by `acct:zachmuhlbauer@hypothes.is` from the past two years (2024-07-15 →).
2. Sort them into an information architecture.
3. Run an automatic routine on every new annotation: Claude **Sonnet 5** places the annotation within the architecture, and tags `revision` / `expansion` / `condense` additionally produce instruction files for the target written artifact / development object.

## Interpretation of the dictated request

- "Codex Intropic" → the Anthropic-powered routine, implemented headlessly via the `claude` CLI (Claude Code print mode).
- "Sonic five" → Claude Sonnet 5 (`claude-sonnet-5`), used for classification per explicit request.
- "webhook runs every single time there is a new annotation" → Hypothesis has **no webhook API**, so the closest faithful mechanism is a launchd agent polling `/api/search` every 5 minutes on an `updated`-timestamp cursor. Latency ≤ 5 min; tag edits to existing annotations also trigger.

## Approaches considered

1. **launchd + `claude -p` (chosen)** — local, no extra API key (uses Claude Code's own auth), survives reboots, files land next to the dissertation workflow. Polling stands in for the webhook.
2. Scheduled cloud agent (Claude routines) — runs off-machine, but can't write to the local IA files that downstream writing work consumes.
3. Python + Anthropic SDK daemon — cleaner API surface (structured outputs), but requires a separate `ANTHROPIC_API_KEY`; the CLI already has authenticated access.

## Architecture

- **Backfill**: `scripts/fetch_annotations.py` paginates `/api/search` (user-filtered, `sort=created asc`, `search_after` cursor) → `data/annotations.jsonl` (225 annotations found in-window; lifetime total 1,703 — older ones excluded per the two-year scope).
- **Initial sort**: `scripts/build_ia.py`, deterministic rules (own-artifact domains ▸ group ▸ domain heuristics) → `architecture/map.jsonl` + generated `overview.md`. Rule-based for the bulk; model judgment reserved for the ongoing stream.
- **Taxonomy**: `architecture/ia.md` — six top-level nodes (artifacts, dissertation, ai-pedagogy, teaching, reading, inbox) with children, grounded in the observed distribution (60 annots on zmuhls.github.io, 29 on localhost:4000 previews, 18 on cuny-ai-lab.github.io; groups: diss, AI FIG, CSC10800…). Cross-cutting workflow axis from tags: revision, expansion, condense, outstanding, resolved (the latter two already in active use — 38/11 occurrences).
- **Watcher**: `scripts/poll.py` — flock-guarded, cursor on `updated`, dedupe via `seen.json`, per-annotation `claude -p --model claude-sonnet-5 --output-format json` with ia.md embedded in the prompt; JSON contract `{node, new_node, role, action}`. Fallback to rule-based placement if the model call fails (`classified_by: rules-fallback`). New-node proposals accumulate in `emergent-nodes.md` for human review; Sonnet cannot invent top-level nodes.
- **Actions**: 17-tag vocabulary (amended 2026-07-15 at user request, from the original 3). Prose & argument: revision, expansion, condense, restructure, hedge, reframe, exemplify, counter, define. Research & evidence: cite, evidence, verify, question, synthesize (synthesize receives sibling annotations at the same node as context). Development objects: bug, feature, a11y. Tags combine — one `actions/<date>-<type>-<id>.md` file per action tag, each with artifact URI, anchor quote, original note, and Sonnet's instructions. Stub file written even if the model omits instructions, so no directive is dropped. Definitions live in `architecture/ia.md` so editing them changes model behavior without code changes.
- **Scheduler**: `launchd/com.zachmuhlbauer.hypothesis-watcher.plist`, StartInterval 300, logs to `logs/`.

## Error handling

Lockfile prevents overlapping runs; per-item cursor advance means a crash resumes where it left off; model failure degrades to rules, never blocks; all activity logged to `logs/watcher.log`.

## Security note

The API token was shared in chat and stored in `config.json` (mode 600). Consider rotating it at https://hypothes.is/account/developer if that exposure is a concern.
