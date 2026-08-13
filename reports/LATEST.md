# Daily maintenance — 2026-08-13

**Health: watcher up, classification still down — same human action pending.** The launchd job is loaded and last exited 0; `poll.py` runs clean against the live API; no new tracebacks. Yesterday's only log entries were a laptop-asleep DNS outage at 18:10 and its recovery at 21:58 — one line each, which is the 08-10 outage handling working as designed. But `claude` still answers **`Failed to authenticate: OAuth session expired and could not be refreshed`**, so a forced live dry-run classified by rules again. **Someone needs to run `claude` and sign in.** No annotations are queued; nothing has been misfiled.

**Adoption — the last hardcoded machine is out of the repo.** `launchd/com.zachmuhlbauer.hypothesis-watcher.plist` carried one person's home directory, anaconda path, and reverse-dns label in a public repo. Deleted, replaced by **`scripts/install_agent.py`**, which renders the unit from whatever checkout you run it in: launchd plist (via stdlib `plistlib`), systemd user `.service` + `.timer`, or a crontab line, with `--label / --python / --interval / --write / --force`. Verified it reproduces the currently-installed plist exactly. The live agent was untouched — it loads from `~/Library/LaunchAgents`, not the repo.

**Adoption — `INSTALL.md`.** From-scratch path: requirements (incl. the `claude` login and the ~$0.10/classification cost), config keys as a table, bootstrap routing, backfill, a dry-run check *before* scheduling, all three schedulers with their verify/pause commands (plus `loginctl enable-linger` and the macOS permission prompt), and a troubleshooting table. README links it and drops the plist row.

**Robustness — logs stop growing forever.** Nothing ever pruned them; `launchd.log` was 205 KB, mostly tracebacks fixed a week ago. Each poll now trims either log past 1 MB down to its last ~250 KB behind a marker line. Rewritten **in place, not renamed** — the scheduler owns an append descriptor on that file and a rename would orphan it; verified the inode survives, on a copy of the real log.

**Verify:** `py_compile` clean, ruff clean, **64/64 tests pass** (13 new, covering unit generation for all three targets and the trim's tail/inode/no-clobber behavior). Live `poll.py` exits 0; a dry-run with the cursor rewound and one `seen` entry dropped forced a real classification attempt, and `data/cursor.json` + `data/seen.json` restored byte-identical (md5-checked).

**Dependencies:** none added. Runtime is still stdlib-only.

**Next candidates (agenda):**
- **ACTION:** run `claude` and sign in — classification stays rules-only until then.
- ADOPTERS: a script that drafts a starter `ia.md` from the adopter's own annotation profile.
- PRO-GRADE: CHANGELOG.md; `pyproject` console entry points (`hypothesis-watch`, `hypothesis-install-agent`); type hints on `poll.py`.
- ROBUSTNESS: per-classification cost visibility (~$0.10 each) in the log, from the CLI's usage envelope; batch handling when many annotations arrive at once (currently one CLI call each, serially).
- DOCS: the 2026-07-15 design spec still names the old plist path.
