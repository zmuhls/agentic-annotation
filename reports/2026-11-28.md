# Daily maintenance — 2026-11-28

**Health: the watcher is up and holding as designed. Both credentials are still dead (Hypothesis token since 11-03, claude CLI login).** The launchd job is loaded (exit 0) and the heartbeat is fresh, reading `status: token` (25 days). `poll.py` and `--dry-run` exit 0 under both the system 3.9 interpreter and the newer one, all 370 tests pass, and ruff and py_compile are clean. `doctor.py --offline` exits 1 on the hold, as intended. The only new log line is today's own dry run, marked `(dry run)`. `cursor.json` stays at the 10-16 cursor, and nothing has been classified or billed.

**Changed: adopters can define their own action tags in `ia.md`.** The 17 tags used to be a list in `build_ia.py`, and the README warned that a tag added only to `ia.md` wrote no file. Now each row of a `| Tag | Directive |` table is a tag: add a row to add a tag, delete one to retire it. Backticks are optional. A tag must be a plain slug, since it names the action file, and the status tags are excluded. An `ia.md` with no usable row falls back to the built-in 17. The local taxonomy and the shipped example both parse to exactly those 17 in the same order, so the live watcher acts the same. `doctor.py` warns about the fallback and names any row it cannot use. There are 16 new tests, and the suite now pins the built-in tags so a local `ia.md` cannot change what it asserts.

**Also:** three July and August reports named the old launchd label, which contains a personal name. Each now says "launchd job" or `<label>`. The old text stays in git history, since force-pushing is ruled out.

**Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, with `claude setup-token` into `claude_env` or by running `claude`. Then `python3 scripts/doctor.py --live` proves it.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`. The github.com credential helper still names a `/usr/local/bin/gh` that does not exist, so pushes need a one-off `-c` override.
- ROBUSTNESS: once the token is back, rewind the cursor for one live `--dry-run` classification, ideally on an annotation with an action tag, to check the full path after six weeks idle.
- PRO-GRADE: one configurable home for `data/` and `config.json` in `appconfig.py`, then a `[project]` table with `requires-python` and console entry points. Leave this for a run where the watcher can be checked end to end.
- DOCS: add a custom-tag example to `docs/examples/` (an `ia.md` row plus the action file it produces), written by the watcher's own `write_action_file` like the others.
