# Daily maintenance — 2026-11-15

**Health: the watcher is up and holding as designed. Both credentials are still dead.** The launchd job is loaded (exit 0) and the heartbeat reads `status: token`. `poll.py` exits 0,  tests pass, and ruff and py_compile are clean. The log has no new entries since yesterday's two cleared network faults. `cursor.json` stays at the 10-16 cursor, as the token hold intends. `doctor.py` still fails the `token` and `claude cli` checks.

**Changed: the personal taxonomy is out of the public tree.** `architecture/ia.md` named one person's groups, sites and projects, and every adopter started with it. It is now gitignored like `config.json` and `routing.json`, and the repo ships `architecture/ia.example.md`, a sample for a fictional account whose node ids match `routing.example.json` (a test holds the two together). While `ia.md` is absent, `poll.py` and the bootstrap scripts read the sample, and `doctor.py` has a new `taxonomy` check that warns about it. `bootstrap.py --write` no longer needs `--force` on a fresh clone. README, INSTALL.md and the CHANGELOG are updated, and the CHANGELOG has an upgrade note, because this pull deletes a tracked `ia.md` in other clones. The live watcher keeps its own `ia.md`, byte-for-byte unchanged. Verified with a dry run and with the full suite in a copy of the tree that has no `ia.md`. The old file remains in git history. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`, because the github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- ROBUSTNESS: add a free check that actually tests the claude login. `claude auth status` reads only local state.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
- DOCS: the README layout table still describes `data/annotations.jsonl` as the maintainer's own two-year pull; reword it for any adopter.
