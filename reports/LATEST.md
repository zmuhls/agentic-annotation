# Daily maintenance — 2026-11-13

**Health: the watcher is up and holding as designed. Both credentials are still dead.** The launchd job is loaded (exit 0) and the heartbeat reads `status: token`. `poll.py` exits 0, 315 tests pass, and ruff and py_compile are clean. The logs show no new faults since 11-12. `cursor.json` stays at the 10-16 cursor, as the token hold intends. `doctor.py` still fails the `token` and `claude cli` checks.

**Changed: the three action-file examples now use fictional pages.** `docs/examples/example-revision.md`, `example-hedge.md` and `example-cite.md` used to quote the maintainer's own drafts and site. In a public repo, that gave adopters an example tied to one person's project. They now come from made-up `example.org` pages: a setup guide for `revision`, and an essay claim tagged `hedge` + `cite`, which shows one annotation producing two files. A scratch script built them with the watcher's own `write_action_file`, so they match what lands in `actions/` byte for byte. The README links all three from the tagging section, and the CHANGELOG notes the change. `poll.py` did not change. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`, because the github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- GENERALIZABILITY: `docs/superpowers/specs/2026-07-15-*.md` is the original design spec, with the maintainer's account, sites and group names. Either mark it as a historical record or trim the personal details.
- ROBUSTNESS: add a free check that actually tests the claude login. `claude auth status` reads only local state.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
