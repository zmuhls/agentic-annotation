# Daily maintenance — 2026-09-20

**Health: the watcher had been dead for four days. Fixed, running, and now classifying again.** `launchctl` reported `last exit code = 78: EX_CONFIG` and nothing had reached `logs/watcher.log` since 09-16. Root cause: the installed launchd unit named `/opt/anaconda3/bin/python3`, and that anaconda install is gone — launchd could not spawn the job at all, so there was no run, no traceback, and no log line. Re-rendered the unit with `install_agent.py --python /usr/bin/python3 --write --force` and reloaded it; it now runs clean (exit 0). Nothing was lost: no annotations arrived in the gap, `data/cursor.json` is intact, and nothing was misfiled.

**The `claude` login is fixed too.** The CLI authenticates again, so the month-old blocker is closed. Confirmed with a forced live dry-run: the one queued annotation came back `classified_by: claude-sonnet-5` with a real node and role, not the rules fallback.

**Why this took four days to notice, and the fix for that.** An empty log is ambiguous — a quiet week and a watcher that never starts look identical. Two changes make the difference visible:

- **`scripts/doctor.py`** (new) checks what silence hides: config keys (never printing the token), the `claude` binary, a launchd/systemd unit *for this checkout* whose interpreter still exists, and heartbeat freshness. Exits non-zero, so it doubles as a cron/CI check.
- **Heartbeat.** Every completed poll stamps `data/health.json` with time, status, count, and how many annotations took the rules fallback. A timestamp that stops advancing is unambiguous where an empty log is not; the fallback count catches a live-but-degraded classifier (the other failure this project has had).
- **`install_agent.py --write` now refuses an interpreter that does not exist**, which is where this bug was installable in the first place. `--allow-missing-python` covers generating a unit for another host. INSTALL.md says to pick an interpreter that outlives a toolchain you might uninstall.

**Verify:** `py_compile` clean, ruff clean, **93/93 tests pass** (29 new, covering unit discovery, a missing interpreter, heartbeat staleness/status/fallbacks, and the install preflight). Live `poll.py` exits 0; `doctor.py` reports four `ok` lines. The forced dry-run restored `data/cursor.json` and `data/seen.json` byte-identical (md5-checked). Also: `.DS_Store` added to `.gitignore`.

**Dependencies:** none added. Runtime is still stdlib-only.

**Next candidates (agenda):**
- ADOPTERS: a script that drafts a starter `ia.md` from the adopter's own annotation profile.
- PRO-GRADE: CHANGELOG.md; `pyproject` console entry points (`hypothesis-watch`, `hypothesis-doctor`); type hints on `poll.py`.
- ROBUSTNESS: per-classification cost visibility (~$0.10 each) in the log, from the CLI's usage envelope; batch handling when many annotations arrive at once (currently one CLI call each, serially).
- DOCS: the 2026-07-15 design spec still names the old plist path.
- MAINTENANCE: ruff *format* has never been run (`ruff format --check` would reformat 9 files); decide whether to adopt it repo-wide in one commit or drop it from the workflow.
