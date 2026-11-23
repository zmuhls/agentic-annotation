# Daily maintenance — 2026-11-23

**Health: the watcher is up and holding as designed. Both credentials are still dead, now three weeks on.** The launchd job is loaded (exit 0) and the heartbeat is fresh, reading `status: token`. `poll.py` exits 0, all 333 tests pass, and ruff and py_compile are clean. The log has nothing new since the 11-15 token line, and `cursor.json` stays at the 10-16 cursor, as the token hold intends. No report was written between 11-17 and 11-22. Nothing has been classified or billed since the hold began.

**Changed: `doctor.py --live` (one script, no change to `poll.py`).** The sign-in check asks `claude auth status`, which reads only the login stored on the machine and cannot tell whether the API still accepts it. `--live` adds one real call through the watcher's own `call_sonnet` path, with a single attempt, and fails with the watcher's own message when it is not answered. It is the only billed check (a few cents at most), so it is opt-in and refuses to combine with `--offline`. Seven new tests cover it, all with a fake call. Run here against the real CLI it failed, at no cost, with `OAuth session expired and could not be refreshed`, which confirms the login is dead and not just reported so. README, INSTALL and CHANGELOG updated. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`. Then `python3 scripts/doctor.py --live` proves it.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`, because the github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- GENERALIZABILITY: let an adopter add action tags. One way is to read extra tags from the Action vocabulary tables in their own `ia.md`, falling back to the built-in 17. This is a design change to the shared contract, so weigh it before building it.
- ROBUSTNESS: a standing fault is logged once per lapse, so a three-week hold leaves one old log line. Consider a reminder line every few days, or a count of days held in the heartbeat detail.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`, and modules that are not installed as top-level `poll`, `doctor` and so on.
