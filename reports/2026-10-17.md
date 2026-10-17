# Daily maintenance — 2026-10-17

**Health: green now, but degraded overnight.** The watcher is loaded (last exit 0) and a kickstarted launchd run on today's code stamped a fresh heartbeat. `doctor.py` reports all `ok`, and `poll.py` and `poll.py --dry-run` exit 0. Four annotations arrived at 23:57–23:59 UTC on 10-16. All four failed with `claude cli is not authenticated (Not logged in)` and were placed by the rules. The CLI reads as signed in now, both in this shell and in a launchd-like clean env. Why the login lapsed is not known. The cursor advanced normally, and the logs show no other errors apart from routine DNS blips.

**Fixed: a dead login no longer files annotations under the rules for good.** Each annotation was marked seen and the cursor moved past it, so signing in again never gave it a model pass. The next idle poll also reset `fallbacks` to 0, so `doctor.py` was back to green within 5 minutes. Now a `ClaudeAuthError` holds the queue the way the daily ceiling does. The cursor stays put, the heartbeat reads `status: auth` with a waiting count, the lapse is logged once rather than every poll, and the first poll after signing in logs `claude cli signed in again` and classifies the queue.

**Changed: `doctor.py` asks `claude auth status`** (local, no model call, nothing spent). It fails when the CLI is signed out. It still passes on the binary alone when the CLI cannot answer, such as an older version. The account email in that output is never printed. Also, a dry run's `processing` line now says `(dry run)`: a maintainer dry run on 10-06 left a bare line that read like a real run that never finished.

**Verify:** 15 new tests, all red before the implementation. 234 pass. Ruff check and format are clean, and py_compile is ok. Cursor and seen were unchanged after the dry run. No paid classification ran.

**Dependencies:** none added; the runtime is still stdlib-only.

**Next candidates:**
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`. A plain `git push` still points at the missing `/usr/local/bin/gh`, so today's push again used a one-off `-c credential.helper` override.
- **OPTIONAL (human):** the four 10-16 annotations keep their rules placement. They carry no action tags, so no action files are affected. To re-run them, drop their ids from `data/seen.json` and set the cursor just before 23:57Z (about 4 calls).
- DOCS: INSTALL says Python 3.11+ and README says CI runs 3.11/3.12, but the watcher runs on 3.9 and CI tests 3.9. Fix the stated floor and add `requires-python` to pyproject.
- ROBUSTNESS: a missing `claude` binary still takes the permanent rules fallback. It is the same systemic shape as a dead login and could hold the queue too.
- PRO-GRADE: console entry points (these first need a configurable home for `data/` and `config.json`).
- ADOPTERS: a worked bootstrap-preview example in `docs/examples/` against fictional groups.
