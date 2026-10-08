# Daily maintenance — 2026-10-08

**Health: green.** The watcher is loaded (last exit 0) and `doctor.py` reports all `ok`. Live `poll.py` and `poll.py --dry-run` both exit 0. The logs have nothing new since the 10-06 DNS outage recovered, and there were no sonnet fallbacks. The cursor is holding because no annotations have arrived.

**Fixed: the backfill could drop annotations at page boundaries** (from the agenda). A live probe showed that `sort=created` truncates `search_after` to milliseconds, the same as `updated`. `fetch_annotations.py` now pages through `poll.fetch_new(key="created")` and retries through `poll.search`. A failed pull exits with the reason and leaves the old file intact. A good pull replaces it in one rename. The script also imports without a `config.json`, and with no `since` it pulls the whole history instead of a hardcoded date. A live pull into scratch returned 226 unique rows, a superset of the July file's 225.

**Fixed: the watcher failed every poll when config had no `since`.** Before any cursor existed, `poll.py` sent `search_after=None`, and the API rejects that with a 400 (probed). Now the first run starts at the current moment and saves that as the cursor, so no billed classification reaches into history unless `since` asks for it. INSTALL.md documents this.

**Verify:** 9 new tests (6 backfill, 3 first-run); 197 pass on the watcher's interpreter (system Python 3.9.6); ruff clean; py_compile ok. The new tests fail on the old code. The dry-run and live polls left cursor, seen, and map checksums unchanged. No paid classification ran.

**Dependencies:** none added; the runtime is still stdlib-only.

**Push still blocked (human fix, 20 days old):** git's credential helper points at `/usr/local/bin/gh`, which is missing. The `gh` on PATH is an unrelated Python package (v0.0.4), not the GitHub CLI. **27 commits are waiting on local `main`.** Install the GitHub CLI (cli.github.com), run `gh auth login`, then `git push origin main`.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper (above).
- MAINTENANCE: commit `ruff format` on its own plus a `ruff format --check` CI step, and add Python 3.9 to the CI matrix (the watcher runs on 3.9), once pushes work.
- PRO-GRADE: `pyproject` console entry points (package `scripts/`); type hints on `poll.py`.
- ROBUSTNESS: have `doctor.py` flag a `since` that isn't ISO 8601 (likely a 400 on every poll too; not probed).
- ADOPTERS: a worked bootstrap-preview example in `docs/examples/` against fictional groups.
