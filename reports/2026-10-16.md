# Daily maintenance — 2026-10-16

**Health: green.** The watcher is loaded (last exit 0). `doctor.py` reports all `ok` with a fresh heartbeat, and both `poll.py` and `poll.py --dry-run` exit 0. The logs since 10-15 hold one DNS blip that recovered within 40 minutes. No sonnet fallbacks, no tracebacks, no spend. The cursor is holding because no annotations have arrived since July.

**Changed: `doctor.py` now verifies the token** (from the agenda). It sends one GET to `/api/profile`, the only endpoint that tells a bad token from a good one: `/api/search` answers an unknown token with public rows and no error. The check fails when `userid` is null, warns when the token belongs to an account other than the one `config.json` watches, and warns (not fails) when the API is unreachable. A placeholder token is never sent. `--offline` skips it, so the checker still works without a network. The call reuses `bootstrap_ia.get` rather than a second HTTP helper. INSTALL.md's troubleshooting row points at it.

**Changed: CI** runs `actions/checkout@v5` and `actions/setup-python@v6` (the Node 24 majors; GitHub deprecated Node 20) and now runs `ruff format --check`. The 16 unformatted files were formatted in a commit of their own so the diff stays mechanical.

**Verify:** 7 new tests, all red before the implementation. 219 pass. Ruff check and format are clean, py_compile is ok. Live `doctor.py` with the real token prints `ok token`; a made-up token prints the fail. Cursor and seen were unchanged after the dry run. No paid classification ran.

**Dependencies:** none added; the runtime is still stdlib-only.

**Push:** a plain `git push` still fails because global git config names the missing `/usr/local/bin/gh`. Pushed with a one-off `-c credential.helper` override, as on 10-15.

**Next candidates:**
- **ACTION (human):** run `~/.local/bin/gh auth setup-git` so a plain `git push` works again.
- PRO-GRADE: console entry points. These first need a configurable home directory for `data/` and `config.json`.
- ADOPTERS: a worked bootstrap-preview example in `docs/examples/` against fictional groups.
- ROBUSTNESS: have `poll.py` record the token check's result in `health.json` once a day, so a revoked token shows in the heartbeat without running doctor.
- MAINTENANCE: `install_agent.py` could emit a `doctor.py --offline` cron line for Linux adopters.
