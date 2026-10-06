# Daily maintenance — 2026-10-06

**Health: green.** Watcher loaded (last exit 0). `doctor.py` reports all `ok`. The live `poll.py` and `poll.py --dry-run` both exit 0. The logs show nothing since the 10-01 DNS outage recovered. No sonnet fallbacks. The cursor holds because no annotations have arrived.

**Changed today: the classifier prompt no longer names the author's node** (generalizability). Its "new child" example was a hardcoded node from one person's taxonomy, and every adopter's model read it on every call. It now uses the first child node in the reader's own `ia.md`, or `<existing-node>/<child>` if there is none. This matches what `bootstrap_ia.draft` already does for the `ia.md` preamble. `bootstrap_ia.nodes_of` is now the shared reader of the nodes section.

**Verify:** 2 new tests; 181 pass; ruff clean; py_compile ok. One live dry-run classification ran with the poll lock held and the cursor rewound ($0.23). It placed the annotation at the same node Sonnet chose originally, and the prompt showed the derived example. Cursor, seen, and map checksums were unchanged afterward, and no action files were written.

**Dependencies:** none added; runtime is still stdlib-only.

**Push still blocked (human fix, now 18 days old).** `~/.gitconfig` sends github.com credentials only to `/usr/local/bin/gh`, which is missing. The `gh` on PATH is an unrelated Python script, not the GitHub CLI. **22 commits are waiting on local `main`.** Install the GitHub CLI from cli.github.com (pkg installer), run `gh auth login`, then `git push origin main`.

**Next candidates:**
- **ACTION (human):** repair the `gh` credential helper (above).
- ROBUSTNESS (low odds): `/api/search` compares `search_after` at millisecond precision (truncated; probed today). `cap_batch` and the budget loop treat only identical microsecond stamps as ties. A batch cut between two annotations in the same millisecond would skip the second. Fix: re-read from the cursor's millisecond start and dedupe through `seen.json`.
- MAINTENANCE: `ruff format` as its own commit, plus a `ruff format --check` CI step, once pushes work. Add Python 3.9 (the macOS system interpreter the watcher runs on) to the CI matrix.
- PRO-GRADE: `pyproject` console entry points (turn `scripts/` into a package); type hints on `poll.py`.
- ADOPTERS: a worked example in `docs/examples/` showing a bootstrap preview against fictional groups.
