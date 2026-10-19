# Daily maintenance — 2026-10-18

**Health: the watcher is up, but the `claude` CLI is now signed out, and someone needs to sign it back in.** The launchd job is loaded (last exit 0). A kickstarted run on today's code stamped `status: ok`, and both `poll.py` and `poll.py --dry-run` exit 0. No annotations have arrived since 10-17. The logs show `api unreachable` from 14:43Z on 10-18 to 03:12Z on 10-19. That window matches the machine sleeping with only brief dark wakes. The outage was logged once and cleared on the first poll after waking.

**Auth lapse found by the live dry run.** One annotation was classified with the cursor and seen rewound, and both files were restored byte for byte afterward. The CLI answered `OAuth session expired and could not be refreshed`. `claude auth status` read signed in 10 minutes earlier and has read signed out ever since. The watcher held the annotation as designed: no rules fallback and nothing marked seen. `doctor.py` now fails its `claude cli` check. The `not authenticated` line at 03:24Z in `watcher.log` came from that dry run, not from launchd.

**Fixed: a missing `claude` binary now holds the queue the way a dead login does.** Before, a moved or uninstalled CLI logged a `FileNotFoundError` and filed every annotation under the rules for good. Now the heartbeat reads `status: no-cli` and names the fixes. `poll.py` and `doctor.py` share one binary lookup (`appconfig.claude_bin`), so doctor no longer fails a `~/.local/bin/claude` that the watcher would find. The recovery log line now reads `claude cli answering again`.

**Added: `"model": "rules"`.** Running without the CLI used to happen only as a side effect of a missing binary. It is now an explicit setting: placement comes from `routing.json` alone, at no cost, and doctor skips its CLI check. **Docs:** the Python floor is stated as 3.9 (it said 3.11), and the README lint steps now match CI.

**Verify:** 8 new tests, all red before the implementation. Two existing tests were updated for the changed messages. 242 tests pass on Python 3.9. Ruff check and format are clean, and py_compile is ok. **Dependencies:** none added; the runtime is still stdlib-only.

**Next candidates:**
- **ACTION (human):** run `claude` and sign in. New annotations wait in the queue until then.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`. Today's push again needed a one-off credential-helper override.
- **OPEN:** it is unknown whether the lapse was the token's own expiry or was triggered by this run. The nested `claude -p` inherited this desktop session's environment (`CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH=1`, `CLAUDE_CODE_CHILD_SESSION=1`), which launchd runs never see. Until that is settled, run live checks under a clean env, e.g. `env -i HOME="$HOME" PATH=/usr/bin:/bin python3 scripts/poll.py --dry-run`.
- ROBUSTNESS: `claude auth status` reads local state only, so it reported signed in for a session that could not refresh. Look for a free check that tells the truth.
- PRO-GRADE: a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
- ADOPTERS: a worked bootstrap-preview example in `docs/examples/` against fictional groups.
