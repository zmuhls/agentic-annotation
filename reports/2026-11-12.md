# Daily maintenance — 2026-11-12

**Health: the watcher is up and holding as designed. Both credentials are still dead.** The launchd job is loaded (exit 0), and the heartbeat was 3 minutes old with `status: token`. `poll.py` and `poll.py --dry-run` both exit 0, 315 tests pass, and ruff and py_compile are clean. The logs show no new faults since 11-11. `cursor.json` stays at the 10-16 cursor, as the token hold intends. `doctor.py` still fails the `token` and `claude cli` checks. Today's push again used a one-off credential-helper override.

**Fixed: an API reply that is JSON but the wrong shape is now treated as a network fault.** A proxy or a sign-in portal can answer with JSON of its own. A bare `"OK"` or a list crashed the scripts with an `AttributeError`. A profile object with no `userid` read as a dead token and told the user to make a new one. A search object with no `rows` read as a quiet `ok` poll that found nothing. `bootstrap_ia.get` now checks each reply against the shape the API sends: a profile carries `userid` (null when anonymous), groups is a list of objects, and a search has a `rows` list. These shapes were confirmed by an anonymous live probe. Anything else raises `ApiReplyError`, so the poll retries it and sets the heartbeat to `api-unreachable`, and `doctor.py` warns instead of blaming the token. 24 tests were written first, and 18 of them failed before the change. **Verified live:** the real profile, groups and search replies all pass the checks, and the poll still reads `token`. A local server answering `{"status": "ok"}` or `"OK"` now gets a one-line exit from `bootstrap_ia.py`, and `ia.md` is left byte-identical.

**Added: `docs/examples/bootstrap-preview.md`**, linked from the README. It shows a real `bootstrap.py` run on fictional groups and `example.*` domains: the preview, the drafted nodes, and the routing tables. It ends with the edits to make before the first poll. A script checked that the document matches the generated output. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`, because the github.com credential helper names a `/usr/local/bin/gh` that does not exist.
- GENERALIZABILITY: the three older `docs/examples/example-*.md` files use the maintainer's own site and draft. Swap in fictional `example.org` content.
- ROBUSTNESS: add a free check that actually tests the claude login. `claude auth status` reads only local state.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
