# Daily maintenance — 2026-10-04

**Health: green.** Watcher loaded (last exit 0); `doctor.py` all `ok`, heartbeat fresh; live `poll.py` exit 0; nothing pending. Since the last run the logs show only DNS outages (09-28 for 5 min, 09-29 to 09-30 for about 4 h overnight, 10-01 for about 4.5 h), and each one recovered on its own. No sonnet fallbacks. The cursor holds because no annotations have arrived since 09-21.

**Changed today: `bootstrap_routing.py` now agrees with `bootstrap_ia.py`** (generalizability). Before, it pointed every group at `inbox`, which left adopters to hand-map each group id to a node in the `ia.md` they had just drafted. INSTALL's troubleshooting table listed "everything lands in inbox" for exactly this reason. Now each group points at its drafted `/general` node, and each busy domain (public ones under `reading`) points at its child node. The script names only node ids that the `ia.md` on disk defines, so running it against someone else's taxonomy gives `inbox` rather than dangling nodes. Both scripts now share one node plan (`bootstrap_ia.plan`) and one node-id reader (`bootstrap_ia.node_ids`). `poll.py` is untouched. README, INSTALL, and CHANGELOG are updated.

**Verify:** `bootstrap_routing.py` had no tests before today. 22 new tests cover node-id parsing, the skeleton, a round trip through `build_ia.node_for`, and `main()` with the API mocked. 167 pass; ruff clean; py_compile ok. An in-memory check against live data (nothing written) routed every group to a real node, with zero dangling nodes.

**Dependencies:** none added; runtime is still stdlib-only.

**Push still blocked (human fix, now 16 days old).** `~/.gitconfig` sends github.com credentials through `/usr/local/bin/gh`, and that file does not exist. The `gh` on PATH is an unrelated Python package, not the GitHub CLI. **17 commits are waiting on local `main`** (18 with this report). Fix: install the GitHub CLI (`brew install gh`), run `gh auth login`, then `git push origin main`.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper.
- MAINTENANCE: `ruff format` would rewrite about 920 lines across 14 files. Deferred: do it as its own commit, with a `ruff format --check` CI step, once the push works.
- PRO-GRADE: `pyproject` console entry points (turn `scripts/` into a package); type hints on `poll.py`.
- ADOPTERS: one `bootstrap` command that runs both drafters in order.
