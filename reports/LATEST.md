# Daily maintenance — 2026-11-03

**Health: the watcher is up and holding correctly, and both credentials are still dead.** The launchd job is loaded (exit 0), and the last heartbeat was minutes old with `status: token`. `poll.py` and `poll.py --dry-run` both exit 0, 271 tests pass, and ruff and py_compile are clean. Since yesterday the logs hold only the expected token-hold lines (one live, one from a dry run). `cursor.json` stays at the 10-16 cursor, as the hold intends. `doctor.py` still fails the `token` and `claude cli` checks.

**Fixed: the bootstrap scripts no longer draft from a dead token.** `bootstrap.py`, `bootstrap_ia.py` and `bootstrap_routing.py` now ask `/api/profile` whose token they hold, one free GET, and exit with nothing written when the answer is nobody. `/api/profile/groups` and `/api/search` answer an unrecognized token as anonymous. The draft then had zero group nodes and still looked finished, and with `--write --force` it would have replaced a working `ia.md` and `routing.json`. The remedy text is now stored once, in `bootstrap_ia.TOKEN_REMEDY`, and `poll.py` imports it from there. 5 tests were written first and failed before the change. **Verified live** against today's dead token: all three scripts exit 1 with the remedy, and `ia.md`, `routing.json`, `cursor.json`, `seen.json` and `annotations.jsonl` are byte-identical. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git` so scheduled pushes need no credential-helper override.
- ROBUSTNESS: have the bootstrap scripts print a one-line message instead of a traceback when the API is unreachable, as `fetch_annotations.py` does.
- ROBUSTNESS: add a free check that actually tests the claude login. `claude auth status` reads only local state.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
- ADOPTERS: add a worked bootstrap-preview example in `docs/examples/` using fictional groups.
