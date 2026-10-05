# Daily maintenance — 2026-10-05

**Health: green.** Watcher loaded (last exit 0). `doctor.py` reports all `ok` and a fresh heartbeat. The live `poll.py` and `poll.py --dry-run` both exit 0. The logs show nothing new since the 10-01 DNS outage, which recovered on its own. No sonnet fallbacks. The cursor holds because no annotations have arrived.

**Changed today: one-step bootstrap** (generalizability; it was on the agenda). Adopters used to run `bootstrap_ia.py`, then `bootstrap_routing.py`. Running them in the wrong order sent every group to `inbox`. The new `scripts/bootstrap.py` runs both from one fetch of groups and annotations. It reads node ids from the `ia.md` it is drafting, so the preview already shows where each group and busy domain will land. It writes both files or neither, and the `--force` guard runs before any API call. The token check the three scripts duplicated is now `bootstrap_ia.require_token`. README, INSTALL, and CHANGELOG are updated.

**Verify:** 12 new tests (one API pass, preview writes nothing, refusal before any call, routing never names a node the drafted `ia.md` lacks). 179 pass; ruff clean; py_compile ok. An in-memory check against live data, with nothing written, gave 0 dangling nodes and 0 groups at inbox. `ia.md` and `routing.json` checksums were unchanged afterward.

**Dependencies:** none added; runtime is still stdlib-only.

**Push still blocked (human fix, now 17 days old).** The cause is the same: `~/.gitconfig` sends github.com credentials only to `/usr/local/bin/gh`, which is missing. **19 commits are waiting on local `main`** (20 with this report). Correction to yesterday: Homebrew is not installed here, so `brew install gh` won't work. Install the GitHub CLI from cli.github.com (pkg installer), run `gh auth login`, then `git push origin main`.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper (above).
- MAINTENANCE: `ruff format` as its own commit, plus a `ruff format --check` CI step, once pushes work.
- PRO-GRADE: `pyproject` console entry points (turn `scripts/` into a package); type hints on `poll.py`.
- ADOPTERS: a worked example in `docs/examples/` showing a bootstrap preview against fictional groups.
