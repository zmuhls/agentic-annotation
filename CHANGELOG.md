# Changelog

Notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project is not
versioned or released yet, so entries are grouped by the date the work landed
on `main`.

## Unreleased

### Added

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
  open-ended, serially billed run; annotations sharing a timestamp are never
  split across the cut, since the next search starts strictly after the cursor.

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

- `scripts/install_agent.py --write` refuses an interpreter that does not exist
  (`--allow-missing-python` covers generating a unit for another host). An
  uninstalled interpreter had silently stopped the watcher for four days.
- `log()` flushes stdout, so a killed run does not lose the buffered lines that
  explain the kill.

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
