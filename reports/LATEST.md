# Daily maintenance — 2026-11-02

**Health: the watcher is up, but the token is dead and the CLI is signed out.** The launchd job is loaded (exit 0). `poll.py` and `poll.py --dry-run` both exit 0, 266 tests pass, and ruff and py_compile are clean. This is the first run since 10-19. The logs since then hold only the usual sleep/wake `api unreachable` blips.

**Found: the Hypothesis token stopped working at some point after 10-19.** `/api/profile` now answers it with `userid: null`, the same as no token at all, and search returns only the 107 public annotations. Private-group annotations have been invisible since then, but the heartbeat still read `ok`. The `claude` CLI is also still signed out.

**Fixed: each poll now asks `/api/profile` before it searches.** That is one free GET per run. When the API does not recognize the token, the poll does not search and the cursor stays put. It logs the problem once, and the heartbeat reads `status: token`, which `doctor.py` reports. Before this, the first public annotation to arrive would have moved the cursor past every unseen private one. The backfill exits on the same check instead of overwriting `annotations.jsonl` with public rows. `search` now goes through a shared retrying `api_get` that reuses `bootstrap_ia.get`. 10 tests were written first, and 9 of them failed before the change. **Verified live:** the hold logged exactly once, and `cursor.json`, `seen.json` and `annotations.jsonl` are byte-identical. **Dependencies:** none added.

**Next candidates:**
- **ACTION (human):** make a new token at hypothes.is/account/developer and put it in `config.json` as `api_token`. The next poll resumes from the held 10-16 cursor.
- **ACTION (human):** sign the CLI in, either with `claude setup-token` into `claude_env` or by running `claude`. Until then, recovered annotations wait in the classifier hold.
- **ACTION (human):** run `~/.local/bin/gh auth setup-git`. Today's push again needed a one-off credential-helper override.
- ROBUSTNESS: give `bootstrap_ia.py` and `bootstrap_routing.py` the same token check. With a dead token they draft from public rows and zero groups.
- ROBUSTNESS: add a free check that actually tests the claude login. `claude auth status` reads only local state.
- PRO-GRADE: add a `[project]` table with `requires-python` and console entry points. This needs a configurable home for `data/` and `config.json`.
- ADOPTERS: add a worked bootstrap-preview example in `docs/examples/` using fictional groups.
