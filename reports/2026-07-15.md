# Daily maintenance — 2026-07-15

**Health:** Watcher up (com.zachmuhlbauer.hypothesis-watcher loaded), scripts compile, `poll.py` exits 0. Cursor steady at 2026-07-06T02:37:04 — no new annotations since. `git pull` clean.

**Fixed — classifier crash on freshly-created annotations.** `watcher.log` showed `sonnet failed for k0n7-…: 'list' object has no attribute 'get'; falling back to rules` at 04:42, then the same annotation classified fine at 04:44. Root cause: the Hypothesis API returns `document` as an empty **list** `[]` for annotations caught mid-creation (before title metadata populates), which crashed `document.get("title")`. Reproduced deterministically; not transient — it will hit every brand-new annotation the poll catches in that window, silently downgrading it to rules-fallback.
- Added `title_of(ann)` in `build_ia.py` that coerces non-dict `document` to `{}`; used it at all three call sites (`record_for`, `classify_prompt`, `write_action_file`).
- Hardened `quote_of` against non-dict `target`/`selector` shapes.
- `process()`'s failure log now records exception type + crash file:line, so the next non-obvious failure is diagnosable instead of guessed.
- Verified: unit repro of all crashing shapes now passes; `classify_prompt` builds on both the real annotation and a synthetic `document=[]` shape; live watcher state untouched (no cursor rewind needed).

**Dependencies:** none added (`traceback` is stdlib).

**Next candidates (agenda):**
- GENERALIZABILITY: move hardcoded `GROUP_NAMES`/`GROUP_NODES`/`ARTIFACT_DOMAINS`/`DH_DOMAINS`/`AIML_DOMAINS` out of `build_ia.py` into config, or fetch groups live from `/api/profile/groups`; move `user`/domains/paths to `config.json`.
- PRO-GRADE: add pytest suite (mock API + `claude` subprocess — no real spend), `ruff`, `pyproject.toml` with console entry point, MIT LICENSE, CHANGELOG.md, GitHub Actions CI. The shape bugs fixed today are exactly what a mocked test suite would have caught.
- ADOPTERS: INSTALL.md covering macOS launchd + Linux systemd/cron; script to bootstrap a starter `ia.md` from a new user's own annotation profile.
- ROBUSTNESS: per-classification cost visibility (~$0.10 each) in the log; batch handling when many annotations arrive at once.
