# Daily maintenance — 2026-09-24

**Health: green.** Watcher loaded (last exit 0); `doctor.py` all `ok`; live `poll.py` and `--dry-run` exit 0; nothing pending. No new errors in either log, only the DNS blips from before 09-17, which recovered on their own.

**Changed today: daily spend ceiling** (robustness and cost). `max_daily_usd` (default `0` = off; `config.example.json` sets 5) caps classification spend per UTC day. `max_per_run` bounds one run, but 288 runs a day with a full queue still add up with no limit. The heartbeat now carries `cost_day` and `cost_usd_today`. Once the day's spend reaches the ceiling, polls stop classifying and the cursor holds, so nothing is skipped. The heartbeat then reads `status: budget` and `doctor.py` warns. Only the run that hits the ceiling logs it. Annotations that share a timestamp are never split at the cut. The live `config.json` is untouched, so the watcher runs as before.

**Verify:** 6 new tests. 142 pass, including a run with the example's $5 ceiling as CI sees it. ruff is clean. No live classification was run, because the classify path did not change.

**Dependencies:** none added; runtime is still stdlib-only.

**Push still blocked (human fix, six days old).** `~/.gitconfig` names `/usr/local/bin/gh` as the github.com credential helper, and that file does not exist. The `gh` on `PATH` is an unrelated Python script. **Fourteen commits are waiting on local `main`.** To fix it, install the GitHub CLI and run `gh auth login`.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper.
- PRO-GRADE: `pyproject` console entry points (turn `scripts/` into a package); type hints on `poll.py`.
- ADOPTERS: have `bootstrap_ia.py` seed `routing.json` from the nodes it writes.
- MAINTENANCE: `ruff format` has never been run (13 files); either adopt it in one commit, with a CI check, or drop it.
- DOCTOR: show today's spend against `max_daily_usd` on the heartbeat line.
