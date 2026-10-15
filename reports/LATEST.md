# Daily maintenance — 2026-10-15

**Health: green.** The watcher is loaded (last exit 0), and `doctor.py` reports all `ok` with a fresh heartbeat. Live `poll.py` and `poll.py --dry-run` both exit 0. The logs since 10-09 hold only DNS/wifi blips, and each recovered on its own. There were no sonnet fallbacks and no tracebacks from the current code. The cursor is holding because no annotations have arrived.

**Push unblocked: all 31 waiting commits are on origin.** The GitHub CLI is now installed at `~/.local/bin/gh` and logged in. The push used a one-off `-c credential.helper=…` override. Global git config is unchanged and still names the missing `/usr/local/bin/gh`, so a plain `git push` still fails. Before pushing, I scanned the unpushed diff for tokens, usernames, and absolute paths and found none. CI's first run since 08-13 is green.

**Changed: a rejected request no longer says "retrying next run"** (from the agenda). `search()` never retries a `4xx` other than `429`, and that request fails every poll until `config.json` changes. The log line now says a retry will not fix it and points at `config.json` and `doctor.py`. A `429` or `5xx` that outlasts the retries still says "retrying next run".

**Found: a bad token is not a 401.** A live probe sent a made-up token, and `/api/search` answered `200` as an anonymous user, with public rows only. A wrong or revoked token therefore drops private-group annotations with no error anywhere. The INSTALL.md troubleshooting row claimed a `401`; it now describes the real symptom.

**Changed: CI** now also runs Python 3.9, the watcher's interpreter, on a pinned `ubuntu-24.04` runner. ubuntu-latest moves to Ubuntu 26 on 10-19, and 3.9 is end-of-life. ruff is pinned to 0.11.2, the version the code is checked with locally. All 3 jobs pass.

**Verify:** 2 new tests; the 401 test failed before the fix. 212 pass locally and in a clean clone with no private config. Ruff is clean and py_compile is ok. A live `400` probe, with every write sent to a scratch directory, printed the new message. Cursor and seen checksums were unchanged. No paid classification ran.

**Dependencies:** none added; the runtime is still stdlib-only.

**Next candidates:**
- **ACTION (human):** run `~/.local/bin/gh auth setup-git` so a plain `git push` works again.
- ROBUSTNESS: `doctor.py` should check the token. Probed today: `GET /api/profile` returns `userid: null` for a bad token and the configured user for a good one.
- MAINTENANCE: bump `actions/checkout` and `actions/setup-python` to their Node 24 majors (CI warns that Node 20 is deprecated).
- MAINTENANCE: commit `ruff format` on its own (16 files), then add a `ruff format --check` CI step.
- PRO-GRADE: console entry points. These first need a configurable home directory for `data/` and `config.json`.
- ADOPTERS: a worked bootstrap-preview example in `docs/examples/` against fictional groups.
