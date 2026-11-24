# Daily maintenance — 2026-11-24

**Health: the watcher is up and holding as designed. Both credentials are still dead (Hypothesis token since 11-03, claude CLI login).** The launchd job is loaded (exit 0), the heartbeat is fresh and reads `status: token`, and `poll.py` and `--dry-run` both exit 0. All 338 tests pass, and ruff and py_compile are clean. The only new log lines since the last report are two network drops on 11-23 (about 5 minutes and 2.5 hours), both of which recovered on their own. `cursor.json` stays at the 10-16 cursor, and nothing has been classified or billed. No live classification test was possible, because the token check runs before any fetch.

**Changed: the heartbeat now says how long a hold has lasted.** A lapse logs one line when it starts, so three weeks on the heartbeat read just as it had five minutes in. Once a token or CLI hold passes a day, `health.json` and `doctor.py` now read `api token not recognized since 2026-11-03 (21 days)`. The start date is the mtime of the marker `note_once` already keeps, so there is no new state and no extra log line.

**Fixed: `poll.main()` held its run lock past return.** A run that caught a CLI failure kept the `flock`, because the caught error's traceback pinned the frame that held it. A second `main()` in the same process then returned without a word. The live watcher was unaffected (each poll is a new process), but one login-lapse test passed with its second poll never running. The lock now sits in a `with` block, and that test now asserts the second poll runs. **Dependencies:** none added.

**Maintainer note:** during debugging, a scratch test run outside `tests/` skipped the conftest isolation and ran four tests against live `data/`. It touched nothing but the heartbeat stamp and one dry-run log line, which was removed. Cursor, seen and markers were unchanged.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, with `claude setup-token` into `claude_env` or by running `claude`. Then `python3 scripts/doctor.py --live` proves it.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`, because the github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- ROBUSTNESS: let `doctor.py` escalate a heartbeat hold from warn to fail once it passes some number of days, now that the age is known.
- GENERALIZABILITY: let adopters add action tags from the vocabulary tables in their own `ia.md`, falling back to the built-in 17. This changes a shared contract, so weigh it before building.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json` first.
