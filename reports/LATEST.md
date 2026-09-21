# Daily maintenance — 2026-09-21

**Health: green.** Watcher loaded and running (last exit 0), heartbeat 0 min old, `doctor.py` four `ok` lines, 100/100 tests pass, ruff clean, live `poll.py` exits 0. Cursor and `seen.json` agree with the API — no annotations pending.

**One mystery, resolved, and it named today's fix.** At 00:56 UTC a run logged `processing 1 new/updated annotation(s)` and then wrote nothing at all: no completion line, no traceback, no cursor advance, no health stamp. It was killed mid-classification — a `claude -p` call can run for minutes, and the scheduler sends `SIGTERM` when the machine sleeps. The tell: that line never reached the scheduler log, whose last write is still 09-16, because stdout to a file is block-buffered and the buffer died with the process. Nothing was lost (the cursor only advances per finished annotation), and the annotation itself has since been deleted from Hypothesis, so there is nothing to re-run. But ruling that out took an hour it should not have.

**Changed today:**

- **Interrupted runs now say so.** `poll.py` catches `SIGTERM`/`SIGINT`, logs where it stopped, and records `status: interrupted` — which `doctor.py` already surfaces as a warning. An unhandled exception anywhere in the poll records `status: error` with the traceback, instead of leaving the previous run's `ok` in place. Verified with a real `SIGTERM` to a real process on isolated paths: exit 143, health stamped, log line written.
- **`log()` flushes stdout,** so a killed run keeps the lines that explain the kill.
- **`CHANGELOG.md`** (agenda item), Keep a Changelog format, entries by date landed.
- **Docs:** the 2026-07-15 design spec's `launchd/com.…plist` path (a file the repo stopped carrying in August) is amended to point at the generated unit; README gains a short paragraph on the two new non-`ok` statuses.

**Verify:** 7 new tests (SIGTERM/SIGINT stamping, dry-run leaving no stamp, crash recorded and logged, both handlers registered) — 100 total. Forced live dry-run at a rewound cursor returned `classified_by: claude-sonnet-5` with a real node and role; `cursor.json` and `seen.json` restored md5-identical.

**Dependencies:** none added. Runtime is still stdlib-only.

**Push is still blocked — same human-only fix as yesterday.** `git push` dies at `/usr/local/bin/gh: No such file or directory`: `~/.gitconfig` sets that broken binary as the *only* credential helper for github.com (its entry resets the list, so the global `store` and system `osxkeychain` never get a turn). I retried via `osxkeychain` explicitly and there is no credential there either. **Seven commits are now waiting on local `main`.** Fix: install the real GitHub CLI (no Homebrew on this machine — use the official installer or `gh` from a release tarball), then `gh auth login`; or repoint `credential."https://github.com".helper` at a helper that has a token.

**Next candidates (agenda):**
- **ACTION (human):** repair the `gh` credential helper; seven commits are stuck locally.
- ADOPTERS: a script that drafts a starter `ia.md` from the adopter's own annotation profile (`bootstrap_routing.py` already does this for `routing.json`).
- PRO-GRADE: `pyproject` packaging + console entry points (`hypothesis-watch`, `hypothesis-doctor`) — needs `scripts/` turned into a real package; type hints on `poll.py`.
- ROBUSTNESS: per-classification cost visibility (~$0.10 each) from the CLI's usage envelope; batch handling when many annotations arrive at once (currently one serial CLI call each, and a long batch is exactly what a sleep `SIGTERM` interrupts).
- MAINTENANCE: `ruff format` has never been run (`--check` would reformat 9 files); adopt it repo-wide in one commit or drop it from the workflow.
