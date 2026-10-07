# Daily maintenance — 2026-10-07

**Health: green.** The watcher is loaded (last exit 0) and `doctor.py` reports all `ok`. Live `poll.py` and `poll.py --dry-run` both exit 0. The only log event is one DNS outage (10-06, 21:58–23:49 UTC), which recovered on its own. No sonnet fallbacks. The cursor is holding because no annotations have arrived.

**Fixed today: annotations in the cursor's millisecond could be skipped for good** (robustness, from the agenda). A live probe confirmed that `/api/search` truncates `search_after` to milliseconds and returns only rows strictly after it, while `updated` carries microseconds. So a `max_per_run` cut, a spend-ceiling stop, or a 200-row page boundary that landed inside one millisecond left the rest of that millisecond behind. Each search now starts one millisecond early (`poll.ms_before`): `seen.json` drops rows already classified, and page overlap is deduped by id. Any cut is now safe, so the tie-keeping special cases in `cap_batch` and the budget loop are gone, and both caps are exact.

**Verify:** 7 new tests, 2 rewritten; 188 pass on the watcher's own interpreter (system Python 3.9.6); ruff clean; py_compile ok. The new end-to-end test fails on the old code (it skips the annotation). A live read-only check showed an idle poll is still one request with 0 fresh rows, so the watcher won't re-bill the cursor row. The dry-run left cursor, seen, and map checksums unchanged. No paid classification was run because the classify path is untouched.

**Dependencies:** none added; the runtime is still stdlib-only.

**Push still blocked (human fix, 19 days old):** git's credential helper points at `/usr/local/bin/gh`, which is missing. **24 commits are waiting on local `main`.** Install the GitHub CLI (cli.github.com), run `gh auth login`, then `git push origin main`.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper (above).
- ROBUSTNESS: the `fetch_annotations.py` backfill has the same page-boundary skip (on `created`). It also has no retries and needs `config.json` (no example fallback). Reuse poll's `search` and the millisecond-restart pagination.
- MAINTENANCE: commit `ruff format` on its own plus a `ruff format --check` CI step, and add Python 3.9 to the CI matrix, once pushes work.
- PRO-GRADE: `pyproject` console entry points (package `scripts/`); type hints on `poll.py`.
- ADOPTERS: a worked bootstrap-preview example in `docs/examples/` against fictional groups.
