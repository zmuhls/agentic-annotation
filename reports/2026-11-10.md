# Daily maintenance — 2026-11-10

**Health: the watcher is up and holding as designed. Both credentials are still dead after a week.** The launchd job is loaded (exit 0), and the heartbeat was 2 minutes old with `status: token`. `poll.py` and `poll.py --dry-run` both exit 0, 277 tests pass, and ruff and py_compile are clean. Since 11-03 the logs show only DNS drops, each one cleared on recovery, and no new faults. `cursor.json` stays at the 10-16 cursor, as the token hold intends. `doctor.py` still fails the `token` and `claude cli` checks. The global git credential helper still names a `gh` that is not there, so today's push again used a one-off override.

**Fixed: the bootstrap scripts exit with one line when the API is down.** `bootstrap.py`, `bootstrap_ia.py` and `bootstrap_routing.py` used to end in a urllib traceback on a dropped connection or a 5xx, and the traceback did not say whether `ia.md` or `routing.json` had been touched. They now print `hypothesis api unreachable (…); nothing drafted` (or `… returned 503 …`), as `fetch_annotations.py` already did. All four scripts share one handler, `bootstrap_ia.api_or_exit`. `api_reason` moved beside it from `poll.py`, which still imports it. 6 tests were written first and failed with a raw `URLError`/`HTTPError` before the change. **Verified live**: all four scripts were run against the real API (dead token, so the expected token message) and through a refused local proxy (the new one-line exit). `ia.md`, `routing.json`, `cursor.json`, `seen.json` and `annotations.jsonl` came out byte-identical. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git` so scheduled pushes need no credential-helper override.
- ROBUSTNESS: add a free check that actually tests the claude login. `claude auth status` reads only local state.
- ROBUSTNESS: a non-JSON 200 (a captive-portal page, for example) still ends the bootstrap scripts in a `JSONDecodeError` traceback.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
- ADOPTERS: add a worked bootstrap-preview example in `docs/examples/` using fictional groups.
