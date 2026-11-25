# Daily maintenance — 2026-11-25

**Health: the watcher is up and holding as designed. Both credentials are still dead (Hypothesis token since 11-03, claude CLI login).** The launchd job is loaded (exit 0) and the heartbeat is fresh, reading `status: token` (22 days). `poll.py` and `--dry-run` both exit 0, all 349 tests pass, and ruff and py_compile are clean. There are no new log lines since the last report. `cursor.json` stays at the 10-16 cursor, and nothing has been classified or billed. A live classification test was not possible, because the token check runs before any fetch.

**Changed: `doctor.py` now fails a credential hold that has lasted more than a day.** A token or CLI hold used to read `warn` however long it lasted. `--offline` skips the token check, so it exited 0 on a token that has been dead for three weeks. `poll.py` now records the hold's start in `health.json` as `held_since`, and doctor reads that field rather than the prose. Holds under a day, network faults and the daily ceiling all stay warnings. Here, `doctor.py --offline` now fails the heartbeat and exits 1.

**Changed: dry-run lines for a token or CLI hold now end in `(dry run)`.** The log lines on 11-10, 11-12, 11-15 and 11-24 that looked like the watcher re-logging the token lapse were the daily review's own dry runs. **Dependencies:** none added.

**Maintainer note:** pushing still needs a one-off `-c credential.…helper` override pointing at `~/.local/bin/gh`. No git config was changed.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, with `claude setup-token` into `claude_env` or by running `claude`. Then `python3 scripts/doctor.py --live` proves it.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`. The github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- ROBUSTNESS: `--dry-run` still writes and clears `data/.netfail`, since `note_network_failure` has no dry-run guard. A dry run during an outage takes the one log line meant for the real watcher.
- GENERALIZABILITY: let adopters add action tags from the vocabulary tables in their own `ia.md`, falling back to the built-in 17. This changes a shared contract, so weigh it before building.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. Start with a single configurable home for `data/` and `config.json` in `appconfig.py`.
