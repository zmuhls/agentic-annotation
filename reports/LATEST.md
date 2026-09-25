# Daily maintenance — 2026-09-25

**Health: green.** Watcher loaded (last exit 0); `doctor.py` all `ok`; live `poll.py` exit 0; nothing pending. The only log entries since the last run are DNS blips on 09-24 (13:56 to 18:59 UTC, several short outages); each recovered on its own on the next poll. No sonnet fallbacks. The cursor has not moved because no new annotations have arrived since the last real one.

**Changed today: spend in `doctor.py`** (cost visibility). The heartbeat line now shows today's spend. With `max_daily_usd` set it reads "$X of $Y daily ceiling used today"; without a ceiling it shows "$X today" only when X is nonzero. A `cost_day` left over from a previous UTC day counts as $0, the same rule `poll.py` uses. Before this, the ceiling from 09-24 could be seen only after it tripped.

**Verify:** 3 new tests; 145 pass; ruff clean; py_compile ok. `poll.py` did not change, so no dry-run classification was needed.

**Dependencies:** none added; runtime is still stdlib-only.

**Push still blocked (human fix, seven days old).** The github.com credential helper in `~/.gitconfig` points to `/usr/local/bin/gh`, which does not exist. **Fifteen commits are waiting on local `main`** (sixteen with this report). Fix: install the GitHub CLI and run `gh auth login`, then `git push origin main`.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper.
- PRO-GRADE: `pyproject` console entry points (turn `scripts/` into a package); type hints on `poll.py`.
- ADOPTERS: have `bootstrap_ia.py` seed `routing.json` from the nodes it writes.
- MAINTENANCE: `ruff format` has never been run; adopt it in one commit with a CI check, or drop it.
