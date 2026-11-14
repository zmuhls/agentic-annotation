# Daily maintenance — 2026-11-14

**Health: the watcher is up and holding as designed. Both credentials are still dead.** The launchd job is loaded (exit 0) and the heartbeat reads `status: token`. `poll.py` exits 0, 315 tests pass, and ruff and py_compile are clean. The only new log entries are two network faults this morning (no route to host, then a DNS failure) that cleared within the hour, which is normal for a laptop. `cursor.json` stays at the 10-16 cursor, as the token hold intends. `doctor.py` still fails the `token` and `claude cli` checks.

**Changed: the original design note is marked as history and no longer names the maintainer's account or sites.** `docs/superpowers/specs/2026-07-15-*.md` described the first single-user build, with one account, its domains and its group names. An adopter reading it could take those for current behavior. It now opens with a note saying it is a historical record and pointing to the README and INSTALL.md, and the personal details are placeholders. The reasoning about polling, the CLI and the fallback is unchanged. The CHANGELOG notes it. No code changed, so no dry run was needed. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`, because the github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- GENERALIZABILITY: the committed `architecture/ia.md` is still the maintainer's own taxonomy, which the live watcher reads. Consider shipping a neutral `ia.example.md` and ignoring the live file, as `config.json` and `routing.json` already do. This needs a migration step so the running watcher keeps its file.
- ROBUSTNESS: add a free check that actually tests the claude login. `claude auth status` reads only local state.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
