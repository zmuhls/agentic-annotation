# Daily maintenance — 2026-10-09

**Health: green.** The watcher is loaded (last exit 0), and `doctor.py` reports all `ok` with a fresh heartbeat. Live `poll.py` and `poll.py --dry-run` both exit 0. The logs since the last run hold only a DNS/network outage (10-08 evening), which recovered at 01:59 UTC on its own. There were no sonnet fallbacks and no tracebacks from the current code. The cursor is holding because no annotations have arrived.

**Improved: API rejections now say why** (from the agenda). A live probe showed that `/api/search` explains a 400 in its error body (e.g. `search_after must be a parsable date…`), but the watcher logged only `400 Bad Request`. The new `poll.api_reason` puts the API's reason into the watcher log, the heartbeat `detail`, and the backfill's exit message. If the body is missing or isn't JSON, only the status is kept. On Python 3.9, an `HTTPError` with no body raises `KeyError` from `read()`, so that case is handled.

**Improved: `doctor.py` flags an unreadable `since`.** The API answers 400 to a value like `garbage` or a 13th month (both probed). It accepts ISO 8601, epoch ms, and some looser forms. A bad `since` fails every poll until a cursor exists, so doctor now warns when the value is neither ISO 8601 nor epoch ms. It says nothing when `since` is fine or unset. INSTALL.md's troubleshooting table and CHANGELOG.md are updated.

**Verify:** 13 new tests, all seen failing first. 210 pass on the watcher's interpreter (system Python 3.9.6) and on the default `python3`. Ruff is clean and py_compile is ok. A live bad request through `api_reason` returned the API's full reason. Cursor and seen checksums were unchanged after the dry-run and live polls. No paid classification ran.

**Dependencies:** none added; the runtime is still stdlib-only.

**Push still blocked (human fix, 21 days old):** git's credential helper for github.com points at `/usr/local/bin/gh`, which is missing. The `gh` on PATH is an unrelated Python package, not the GitHub CLI. **29 commits are waiting on local `main`.** Install the GitHub CLI (cli.github.com), run `gh auth login`, then `git push origin main`.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper (above).
- MAINTENANCE: commit `ruff format` on its own (16 files), add a `ruff format --check` CI step, and add Python 3.9 to the CI matrix. 3.9 is end-of-life, so on the first push check that `setup-python` still serves it on `ubuntu-latest`; if not, pin `ubuntu-22.04`.
- PRO-GRADE: console entry points. Blocker: the scripts find `data/` and `config.json` relative to their own file, so an installed package first needs a configurable home directory.
- ROBUSTNESS: a 4xx (400/401) is still logged as "retrying next run". It will not heal on retry, so point to `config.json` instead.
- ADOPTERS: a worked bootstrap-preview example in `docs/examples/` against fictional groups.
