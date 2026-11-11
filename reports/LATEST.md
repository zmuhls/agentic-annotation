# Daily maintenance — 2026-11-11

**Health: the watcher is up and holding as designed. Both credentials are still dead.** The launchd job is loaded (exit 0), and the heartbeat was 2 minutes old with `status: token`. `poll.py` and `poll.py --dry-run` both exit 0, 291 tests pass, and ruff and py_compile are clean. The logs show no new faults since 11-10. `cursor.json` stays at the 10-16 cursor, as the token hold intends. `doctor.py` still fails the `token` and `claude cli` checks. The global git credential helper still names a `gh` that is not there, so today's push again used a one-off override.

**Fixed: an API reply that is not JSON or is cut off no longer crashes the scripts.** A wifi sign-in page or a proxy can answer 200 with HTML, and a dropped link can cut a body short (`IncompleteRead`). Neither raises an `OSError`, so both skipped every network handler. The poll ended in a traceback with health set to `error`, and the bootstrap scripts and the backfill ended in a `JSONDecodeError` traceback. `bootstrap_ia.get`, which every script reads replies through, now raises `ApiReplyError`, an `OSError` that names the endpoint. The poll retries it like a DNS drop, logs one line and sets health to `api-unreachable`. The other scripts exit with that same line. `poll.py` itself did not change. 14 tests were written first, and 13 of them failed before the change. **Verified live:** `bootstrap_ia.py` and `poll.py` were pointed at a local server that answers with an HTML page, using a fake token and scratch paths. The old code gave a `JSONDecodeError` traceback and the new code gives a one-line exit. The real `ia.md`, `routing.json` and `data/` files came out byte-identical. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git` so scheduled pushes need no credential-helper override.
- ROBUSTNESS: a JSON reply of the wrong shape (a list, or a string) still raises `AttributeError` at `.get(...)` in `token_owner` and `require_recognized`.
- ROBUSTNESS: add a free check that actually tests the claude login. `claude auth status` reads only local state.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
- ADOPTERS: add a worked bootstrap-preview example in `docs/examples/` using fictional groups.
