# Changelog

Notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project is not
versioned or released yet, so entries are grouped by the date the work landed
on `main`.

## Unreleased

### Added

- `scripts/bootstrap.py` runs both drafters as one step: one fetch of the
  adopter's groups and recent annotations, the routing's node ids read off the
  `ia.md` being drafted rather than the one on disk, and both files written or
  neither. The preview prints where each group and busy domain will land, so
  the pair can be checked before anything is written, and the `--force` guard
  runs before any API call. The token check the three bootstrap scripts share
  is now one function, `bootstrap_ia.require_token`.

- `bootstrap_routing.py` drafts a `routing.json` that agrees with the `ia.md`
  `bootstrap_ia.py` drafted: each group points at its `/general` node and each
  busy domain at its child node, instead of every group starting at `inbox` and
  waiting to be hand-mapped. It names only node ids the `ia.md` on disk defines,
  so a taxonomy that is not yours yields `inbox` rather than dangling nodes.
  Both scripts share one node plan (`bootstrap_ia.plan`) and one reader of the
  node ids an `ia.md` defines (`bootstrap_ia.node_ids`).

- `doctor.py` shows today's classification spend on the heartbeat line, as
  "$X of $Y daily ceiling used today" when `max_daily_usd` is set, so the
  budget is visible before it trips rather than only after.

- A daily spend ceiling (`max_daily_usd` in `config.json`, default `0` = off).
  The heartbeat now tracks spend per UTC day (`cost_day`, `cost_usd_today`);
  once the day reaches the ceiling, polls classify nothing, hold the cursor, and
  stamp `status: budget`, which `doctor.py` surfaces as a warning. Only the run
  that hits the ceiling logs it.

- A per-run batch cap (`max_per_run` in `config.json`, default 25). A backlog
  larger than the cap is classified across successive polls rather than in one
  open-ended, serially billed run.

- `scripts/doctor.py`: a one-shot health check (config keys, `claude` binary,
  a scheduler unit for *this* checkout whose interpreter still exists,
  heartbeat freshness). Exits non-zero, so it doubles as a cron or CI check.
- A heartbeat: every completed poll stamps `data/health.json` with the time,
  status, annotations processed, and how many took the rules fallback. A
  timestamp that stops advancing is unambiguous where an empty log is not.
- Interrupt and crash reporting in `scripts/poll.py`. A poll killed by the
  scheduler mid-classification (`SIGTERM` on sleep or unload) now logs where it
  stopped and records `status: interrupted`; an unhandled exception records
  `status: error` with the traceback instead of leaving a stale `ok`.
- `scripts/bootstrap_ia.py`: drafts `architecture/ia.md` from the adopter's own
  groups and annotated domains, carrying the shared action-tag vocabulary over
  from the existing file. The committed taxonomy is one person's, and it is the
  file the classifier reads on every poll — an adopter who leaves it in place
  sorts their annotations into someone else's projects.
- Cost visibility. `poll.py` records the `total_cost_usd` the `claude` CLI
  reports for each classification onto that annotation's map record and log
  line, and `data/health.json` carries a per-run figure and a lifetime total
  that `doctor.py` prints beside the heartbeat.
- `CHANGELOG.md` (this file).

### Changed

- The classifier prompt draws its "new child" example from the first child node
  in your own `ia.md` (`<existing-node>/<child>` if it has none). It used to
  name one author's node on every call, a node most other taxonomies lack.
  `bootstrap_ia.nodes_of` is the shared reader of an `ia.md`'s nodes section.
- `scripts/install_agent.py --write` refuses an interpreter that does not exist
  (`--allow-missing-python` covers generating a unit for another host). An
  uninstalled interpreter had silently stopped the watcher for four days.
- `log()` flushes stdout, so a killed run does not lose the buffered lines that
  explain the kill.

### Fixed

- Annotations stamped in the same millisecond as the cursor are no longer
  skipped. `/api/search` truncates `search_after` to milliseconds and returns
  rows strictly after it, while `updated` carries microseconds, so a batch cap,
  a spend stop, or a 200-row page boundary that fell inside one millisecond
  stranded the rest of it for good. Each search now starts one millisecond
  early (`poll.ms_before`) and `seen.json` drops the rows already done. That
  makes any cut safe, so `max_per_run` and `max_daily_usd` no longer stretch to
  keep identical timestamps together. An idle poll is still one request.
- The backfill (`scripts/fetch_annotations.py`) had the same skip on `created`
  (probed live: that sort truncates to milliseconds too) and gave up on the
  first dropped connection. It now pages through `poll.fetch_new(...,
  key="created")` and retries through `poll.search`. A failed pull exits with
  the reason and leaves the previous `data/annotations.jsonl` intact, and the
  new file replaces the old one in a single rename. It also no longer needs a
  `config.json` just to be imported (tests and CI fall back to the example),
  and without a `since` it pulls the whole history instead of a hardcoded date.
- A `config.json` without `since` no longer breaks the watcher. With no saved
  cursor either, `poll.py` asked `/api/search` for `search_after=None`, which
  the api rejects with 400, so every run failed. The first run now starts from
  the current moment and saves it as the cursor (`poll.start_cursor`), so
  nothing billed reaches into history unless `since` asks for it.

## 2026-08-13

### Changed

- `scripts/install_agent.py` generates the scheduler unit (launchd plist or
  systemd user timer) instead of the repo carrying one maintainer's plist.
- Oversized logs are trimmed in place rather than growing without bound.

### Added

- `INSTALL.md`: a from-scratch adoption path for macOS and Linux.

## 2026-08-11

### Changed

- Placement tables (group ids, artifact domains, domain heuristics) moved out of
  code into a gitignored `routing.json`, with `routing.example.json` as the
  template. `scripts/bootstrap_routing.py` drafts one from an adopter's own
  annotation profile.
- `claude` CLI auth failures are reported from the JSON envelope the CLI writes
  to stdout, and fail fast instead of burning retries.

## 2026-08-10

### Added

- MIT `LICENSE`, `ruff` configuration, and a GitHub Actions CI workflow running
  lint and tests.

### Changed

- Transient network faults in the poll path are retried; an outage is logged
  once per outage rather than once per five-minute run.

## 2026-07-15

### Added

- Initial system: `scripts/poll.py` polls the Hypothesis API on an `updated`
  cursor, classifies each new or updated annotation with Claude Sonnet 5 into
  the taxonomy in `architecture/ia.md`, and writes one instruction file per
  action tag into `actions/` (17-tag vocabulary).
- `scripts/fetch_annotations.py` (backfill) and `scripts/build_ia.py`
  (deterministic initial placement).
- A mocked pytest suite: the `claude` CLI and the Hypothesis API are always
  faked, so the suite never spends API money.
