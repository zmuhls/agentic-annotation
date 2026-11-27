# Daily maintenance — 2026-11-27

**Health: the watcher is up and holding as designed. Both credentials are still dead (Hypothesis token since 11-03, claude CLI login).** The launchd job is loaded (exit 0) and the heartbeat is fresh, reading `status: token` (24 days, `held_since` set). `poll.py` and `--dry-run` both exit 0, all 354 tests pass, and ruff and py_compile are clean. `doctor.py --offline` exits 1 on the hold, as intended since 11-25. The only new log line since the last report is today's own dry run, marked `(dry run)`. `cursor.json` stays at the 10-16 cursor, and nothing has been classified or billed.

**Changed: `--dry-run` no longer writes or clears `data/.netfail`.** Each outage gets one log line, kept by a marker file. During an outage, a dry run wrote that marker, so the real watcher's next run found the message already recorded and logged nothing. After recovery, a dry run unlinked it, so the watcher never logged `reachable again`. A dry run now logs the fault ending in `(dry run)` and leaves the marker alone, as it already did for the token and CLI holds. Five new tests cover both directions and both error paths (unreachable, HTTP 503). The live run here could not reach this path, because the API is reachable and the token check fails first.

**Dependencies:** none added.

**Maintainer note:** pushing still needs a one-off `-c credential.…helper` override pointing at `~/.local/bin/gh`. No git config was changed.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, with `claude setup-token` into `claude_env` or by running `claude`. Then `python3 scripts/doctor.py --live` proves it.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`. The github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- PRO-GRADE: one configurable home for `data/` and `config.json` in `appconfig.py`, then a `[project]` table with `requires-python` and console entry points. Leave this for a run where the watcher can be checked end to end.
- GENERALIZABILITY: let adopters add action tags from the vocabulary tables in their own `ia.md`, falling back to the built-in 17. This changes a shared contract, so weigh it before building.
- ROBUSTNESS: once the token is back, rewind the cursor for one live `--dry-run` classification to recheck the full poll-classify path after six weeks idle.
