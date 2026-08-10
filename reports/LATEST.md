# Daily maintenance — 2026-08-10

**Health:** Watcher loaded and running (last exit 0), scripts compile, `poll.py` exits 0 against the live API (no new annotations; cursor steady at 2026-07-16T18:17:26). `git pull` clean. `logs/watcher.log` shows no failures since the last run — the two July `sonnet failed` lines are the known stale/test entries, not live faults.

**Fixed — transient network faults were crashing the watcher.** `logs/launchd.log` holds 126 tracebacks, 120 of them from one cause: `search()` let any `urlopen` error escape, so a sleeping laptop or a wifi drop killed the run with a 30-line traceback (36× DNS failure, 8× no route to host, 5× connection reset, plus SSL EOF/handshake/read timeouts). `search()` now retries three times with exponential backoff (5s, 10s — well inside the 5-minute interval) on `OSError` and on `429`/`5xx`, while real faults (`401` bad token, `400` bad query) still raise at once. `main()` catches the exhausted case, logs one line, and exits cleanly. The message is written once per outage rather than once per poll (a marker in `data/.netfail`, cleared with a "reachable again" line on recovery) — otherwise a wifi drop would write 288 identical lines a day into the log this review reads. Verified by simulating three consecutive failing polls: one log line, no traceback, exit 0.

**Added from the agenda — MIT LICENSE, ruff, CI.** `pyproject.toml` gains a `[tool.ruff]` section (E,F,W,I,UP,B; `E501` off because the Sonnet prompt is prose inside an f-string and rewrapping it would change what the model reads); fixed the resulting findings (ambiguous `l` loop var ×4, an unused `ACTION_TAGS` import, import sorting). `.github/workflows/ci.yml` runs `ruff check .` and `pytest` on Python 3.11 and 3.12 for every push and PR. README documents lint, CI, the network-fault behavior, and the license.

**Verify:** `py_compile` clean; ruff clean; **40/40 tests pass** (5 new: retry-then-succeed, exhausted attempts, retry-429-but-not-401, log-once-per-outage, clear-is-noop). Rehearsed CI on a clean tracked-files-only checkout — ruff and pytest both green with no `config.json`. `poll.py` live run and `--dry-run` both exit 0; cursor, seen, and watcher log untouched. No private files staged.

**Dependencies:** none. `ruff` joins `pytest` as dev/CI-only; runtime stays stdlib-only.

**Next candidates (agenda):**
- GENERALIZABILITY (top priority, still untouched): move hardcoded `GROUP_NAMES`/`GROUP_NODES`/`ARTIFACT_DOMAINS`/`DH_DOMAINS`/`AIML_DOMAINS` out of `build_ia.py` into config, or fetch groups live from `/api/profile/groups`; get `user`/domains/paths from `config.json`.
- ADOPTERS: INSTALL.md (macOS launchd + Linux systemd/cron); a script that bootstraps a starter `ia.md` from a new user's own annotation profile.
- PRO-GRADE: CHANGELOG.md; full `pyproject` packaging with console entry points; type hints on `poll.py`.
- ROBUSTNESS: per-classification cost visibility (~$0.10 each) in the log; batch handling when many annotations arrive at once; rotate/truncate `logs/launchd.log` (205 KB, mostly the tracebacks now fixed).
