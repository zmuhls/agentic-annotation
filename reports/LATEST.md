# Daily maintenance — 2026-09-22

**Health: green.** Watcher loaded, last exit 0; `doctor.py` four `ok` lines; heartbeat fresh; 131 tests pass; ruff clean; live `poll.py` exits 0. Cursor and `seen.json` agree with the API — nothing pending.

**Two log lines that looked like yesterday's ghost, weren't.** `watcher.log` holds a bare `processing 1 new/updated annotation(s)` at 09-21 12:16 with no completion line. That was yesterday's own forced dry-run: a dry run logs the opening line, prints its JSON to stdout, and writes nothing else by design. The 00:56 entry beside it is the `SIGTERM` already explained and already instrumented. No fault, nothing to fix.

**Changed today — both from the standing agenda:**

- **`scripts/bootstrap_ia.py`** (adopters, top priority). `architecture/ia.md` is the last hardcoded personal artifact in the repo, and it is the file the classifier reads on every poll: an adopter who clones and leaves it in place sorts their own annotations into the maintainer's projects. The script asks `/api/profile/groups` and a 200-annotation sample where they actually annotate, then rewrites the nodes section as one top-level node per group, each group's busiest domains (≥2 hits) as children, public-layer reading under `reading`, and `inbox`. The action-tag vocabulary below it is the same for everyone — `poll.py` and `build_ia.py` implement it — so it carries over verbatim instead of being restated in Python. The preamble's account and its example node id are rewritten too. Same `--write` / `--force` contract as `bootstrap_routing.py`.
- **Per-classification cost visibility.** The `claude` CLI already reports `total_cost_usd` in its result envelope and the watcher was throwing it away. It now lands on the annotation's map record, on its log line, and in `data/health.json` as a per-run figure plus a lifetime total that `doctor.py` prints beside the heartbeat. Nothing estimates or prices tokens; a rules fallback costs and records nothing.
- **Real number, worth knowing:** the verification call billed **$0.187**, not the ~$0.10 the agenda assumed. At that rate the tally matters more than it looked like it would.

**Verify:** 22 new tests (slug collisions, domain thresholds, vocabulary carried through, both envelope shapes, lifetime tally, corrupt-stamp recovery) — 131 total, ruff clean. One live classification through the changed path returned `classified_by: claude-sonnet-5` with a real node, role, and `cost_usd`, run on throwaway paths so the five-minute watcher could fire mid-run without colliding; `cursor.json` and `seen.json` md5-identical before and after. The scheduled 14:02 poll then ran the new code on its own and stamped the new fields.

**Dependencies:** none added. Runtime is still stdlib-only.

**Push is still blocked — same human-only fix, now four days old.** `git push` dies at `/usr/local/bin/gh: No such file or directory`, which `~/.gitconfig` names as the *only* credential helper for github.com. The `gh` on `PATH` is an unrelated Python script, not the GitHub CLI. **Eleven commits are now waiting on local `main`.** Fix: install the real GitHub CLI and `gh auth login`, or repoint `credential."https://github.com".helper` at a helper that holds a token.

**Next candidates (agenda):**
- **ACTION (human):** repair the `gh` credential helper; eleven commits are stuck locally.
- PRO-GRADE: `pyproject` packaging + console entry points (`hypothesis-watch`, `hypothesis-doctor`) — needs `scripts/` turned into a real package; type hints on `poll.py`.
- ROBUSTNESS: batch handling when many annotations arrive at once (one serial CLI call each today, and a long batch is exactly what a sleep `SIGTERM` interrupts); a spend ceiling per run now that the real per-call price is known.
- ADOPTERS: `bootstrap_ia.py` could seed `routing.json` directly from the nodes it just wrote, instead of leaving every group at `inbox` for hand-mapping.
- MAINTENANCE: `ruff format` has never been run (`--check` would reformat 9 files); adopt it repo-wide in one commit or drop it from the workflow.
