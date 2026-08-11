# Daily maintenance — 2026-08-11

**Health: watcher up, but Sonnet classification is down — needs a human.** The launchd job is loaded and `poll.py` exits 0 against the live API; no new tracebacks since yesterday (still 126, all pre-fix), and the network-fault handling added on 08-10 held. But a dry-run classification failed with `claude exited 1` and an empty stderr, and running the CLI by hand gave the reason: **`Failed to authenticate: OAuth session expired and could not be refreshed`**. Until someone runs `claude` and signs in again, every annotation is placed by the rules and recorded as `rules-fallback` — the watcher keeps working, it just stops thinking. No annotations are waiting, so nothing has been misfiled yet.

**Fixed — failures that say nothing.** The CLI reports auth/API errors as a JSON envelope on *stdout* and leaves stderr empty, so `call_sonnet` logged a bare `claude exited 1: ` for every past failure (which is why the July entries were undiagnosable). It now digs the message out of the envelope, and treats an auth failure as terminal instead of sleeping 30s and retrying a login that cannot heal itself.

**Generalizability — the personal routing tables are out of the code.** `build_ia.py` carried 24 group ids, own-site domains, and reading-list domains as literals in a public repo. They now live in a gitignored `routing.json`, loaded by a new `scripts/appconfig.py` (shared with `poll.py`, replacing its private config loader). `routing.example.json` documents the schema and the order the six tables are consulted in; the two special cases that were `if` statements — own-artifacts-beat-group, and one group whose node depends on the site — are now `artifact_domains` and `group_domain_overrides` entries, so anyone can express them. The prompt's owner name comes from `config.json` too. **Verified by replaying all 225 real annotations through old and new `node_for`: 0 placement differences, 0 group-name differences.**

**Adopters — `scripts/bootstrap_routing.py`.** Asks `/api/profile/groups` for your own groups and drafts a `routing.json` with each one named and pointed at `inbox`, ready to edit (`--write`, refuses to clobber without `--force`). Verified live: 25 groups. README gains an "Adopting it for your own annotations" section and a troubleshooting note for the auth failure above.

**Verify:** `py_compile` clean, ruff clean, **51/51 tests pass** (11 new). The suite is now hermetic — routing assertions use fictional tables from a `conftest.py` fixture instead of the maintainer's real groups, so it no longer breaks when a group is re-mapped. Rehearsed CI on a tracked-files-only checkout with neither `config.json` nor `routing.json`: green. Live `poll.py` and `--dry-run` both exit 0; cursor and seen restored byte-identical after the rewind test.

**Dependencies:** none added. Runtime is still stdlib-only.

**Next candidates (agenda):**
- **ACTION:** run `claude` and sign in — classification stays rules-only until then.
- ADOPTERS: INSTALL.md (macOS launchd + Linux systemd/cron); a script that drafts a starter `ia.md` from the adopter's own annotation profile; make the launchd plist's absolute paths and label generated rather than committed.
- PRO-GRADE: CHANGELOG.md; `pyproject` console entry points; type hints on `poll.py`.
- ROBUSTNESS: per-classification cost visibility (~$0.10 each) in the log; batch handling when many annotations arrive at once; rotate/truncate `logs/launchd.log` (205 KB, mostly the tracebacks now fixed).
