# Daily maintenance — 2026-09-23

**Health: green.** Watcher loaded (last exit 0); `doctor.py` all `ok`, heartbeat fresh; live `poll.py` and `--dry-run` exit 0; nothing pending (cursor and `seen.json` agree with the API). No errors in either log since the last run, only the familiar DNS blips before 09-17, which recovered on their own.

**Changed today: per-run batch cap** (robustness and cost). `max_per_run` in `config.json` (default 25, `0` = no limit) bounds how many annotations one poll classifies. Before this, a backlog (a new adopter with an old `since`, or a bulk re-tag) became one serial run billed at roughly $0.19 per call, open-ended and held under the poll lock for as long as it took. That long run is also the window a sleep `SIGTERM` interrupts. Deferred annotations are picked up on later runs. The cut never splits a shared `updated` timestamp, because the next search starts strictly after the cursor and would skip the second one. The log line and the heartbeat `detail` both report how many were deferred. Documented in README, INSTALL, CHANGELOG, and `config.example.json`.

**Verify:** 5 new tests, including an end-to-end `main()` check that the cursor, `seen.json`, and the heartbeat stop at the cap. 136 pass, ruff clean. No live classification was run, because only the batch loop changed and the classify path did not.

**Dependencies:** none added; runtime is still stdlib-only.

**Push is still blocked (human fix, five days old).** `~/.gitconfig` names `/usr/local/bin/gh` as the only github.com credential helper, and that file does not exist. The `gh` on `PATH` is an unrelated Python script. **Twelve commits are waiting on local `main`.** To fix it, install the GitHub CLI and run `gh auth login`, or point `credential."https://github.com".helper` at a working helper.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper.
- PRO-GRADE: `pyproject` console entry points (`hypothesis-watch`, `hypothesis-doctor`), which need `scripts/` to become a package; type hints on `poll.py`.
- ROBUSTNESS: a daily or lifetime spend ceiling in dollars, alongside the count cap.
- ADOPTERS: have `bootstrap_ia.py` seed `routing.json` from the nodes it writes.
- MAINTENANCE: `ruff format` has never been run (9 files); either adopt it in one commit or drop it.
