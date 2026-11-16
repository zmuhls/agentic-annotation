# Daily maintenance — 2026-11-16

**Health: the watcher is up and holding as designed. Both credentials are still dead.** The launchd job is loaded (exit 0) and the heartbeat reads `status: token`. `poll.py` exits 0, all 326 tests pass, and ruff and py_compile are clean. The log has nothing new since the 11-15 token line. `cursor.json` stays at the 10-16 cursor, as the token hold intends. `doctor.py` still fails the `token` and `claude cli` checks.

**Changed: the README now matches the code (docs only, no script touched).** The intro and diagram said only `revision`, `expansion` and `condense` produce action files, when all 17 action tags do. The tag section told adopters to edit the vocabulary in `ia.md`. That would not work: the tags that produce files are fixed in `build_ia.py` (`bootstrap_ia.split_template` calls them a shared contract), and `ia.md` only words each directive. The README now says so, including that a tag added only to `ia.md` produces no file. The layout table described one person's two-year backfill and marked some gitignored files but not others. It now has one note listing everything gitignored, plus rows for `config.example.json`, `watcher.log` and `launchd.log`. The file map in `ia.example.md` lists every `map.jsonl` field and no longer limits `actions/` to three tags. The live `ia.md` is untouched. CHANGELOG updated. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`, because the github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- GENERALIZABILITY: let an adopter add action tags. One way is to read extra tags from the Action vocabulary tables in their own `ia.md`, falling back to the built-in 17. This is a design change to the shared contract, so weigh it before building it.
- ROBUSTNESS: add a check that actually tests the claude login. `claude auth status` reads only local state, and a live check costs a small model call, so it would have to be opt-in (`doctor.py --live`).
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`, and modules that are not installed as top-level `poll`, `doctor` and so on.
