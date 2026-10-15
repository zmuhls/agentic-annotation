# Hypothesis Annotation System

Pulls every Hypothesis annotation by a given account, sorts it into an
information architecture, and watches for new annotations — each new or
edited annotation is classified into the architecture by **Claude Sonnet 5**,
and annotations tagged `revision`, `expansion`, or `condense` generate
concrete instruction files for the target written artifact or development
object.

## How it works

```
Hypothesis API ──(poll every 5 min, cursor on `updated`)──▶ scripts/poll.py
                                                                │
                       claude -p --model claude-sonnet-5 ◀──────┤ per annotation
                                                                │
              ┌─────────────────────────────────────────────────┤
              ▼                          ▼                      ▼
   architecture/map.jsonl       actions/<date>-<type>-<id>.md   logs/watcher.log
   (node + role per annotation) (revision/expansion/condense)
```

Hypothesis offers no webhooks, so a launchd agent polls every 5 minutes —
the closest thing to "runs every single time there is a new annotation."
Because the cursor tracks `updated` (not `created`), **adding a tag like
`revision` to an old annotation also triggers the routine**. The API compares
the cursor only to the millisecond, so each search re-reads the cursor's own
millisecond and `data/seen.json` skips what is already classified; a run cut
short anywhere resumes without losing an annotation.

## Layout

| Path | Purpose |
|---|---|
| `config.json` | API token, user, owner label, model, backfill start date (chmod 600) |
| `routing.json` | Your placement tables — group ids, own-artifact domains (gitignored) |
| `routing.example.json` | Documented schema and precedence for the above |
| `data/annotations.jsonl` | Raw two-year pull (2024-07-15 →) |
| `data/cursor.json`, `data/seen.json` | Watcher state |
| `architecture/ia.md` | The taxonomy — hand-editable; Sonnet reads it on every classification |
| `architecture/map.jsonl` | One record per annotation: node, workflow, role, quote, note, link |
| `architecture/overview.md` | Generated per-node counts |
| `architecture/emergent-nodes.md` | Sub-nodes Sonnet proposed; review and fold into ia.md |
| `actions/` | Generated instruction files for tagged editorial directives |
| `scripts/appconfig.py` | Loads `config.json` / `routing.json` with `.example` fallbacks |
| `scripts/bootstrap.py` | Runs both drafters below in one step, from one API pass |
| `scripts/bootstrap_ia.py` | Drafts an `architecture/ia.md` from your own annotation history |
| `scripts/bootstrap_routing.py` | Drafts a `routing.json` from your own Hypothesis groups |
| `scripts/fetch_annotations.py` | Full re-pull (backfill) |
| `scripts/build_ia.py` | Rule-based initial sort of the backfill |
| `scripts/poll.py` | The watcher + Sonnet 5 classifier |
| `scripts/install_agent.py` | Generates the scheduler unit (launchd / systemd / cron) |
| `scripts/doctor.py` | Health check: is the watcher scheduled, alive, and classifying? |
| `data/health.json` | Heartbeat written by every completed poll (gitignored) |

## Adopting it for your own annotations

**[INSTALL.md](INSTALL.md) is the full path** — requirements, config, backfill,
scheduling on macOS/Linux, and troubleshooting. The short version:

Nothing personal is compiled into the code. Two gitignored files hold everything
that differs between people:

```sh
cp config.example.json config.json && chmod 600 config.json
# fill in api_token (hypothes.is → Developer), user (acct:you@hypothes.is), owner

python3 scripts/bootstrap.py                  # preview where each group will land
python3 scripts/bootstrap.py --write --force  # your taxonomy and routing, from your own history
```

The committed `architecture/ia.md` is the maintainer's taxonomy, and it is what
the classifier reads on every poll, so replace it first. `bootstrap.py` runs two
drafters in order, from one fetch of your groups and recent annotations, and
writes both files or neither. The first, `bootstrap_ia.py`, rewrites the nodes
section as one node per group you belong to, each group's busiest domains as
children, and your public reading under `reading`. The action-tag vocabulary
below it is the same for everyone and carries over untouched. Then
`bootstrap_routing.py` writes a `routing.json` naming every group and pointing
each group, and each of its busiest domains, at the node `bootstrap_ia.py` just
drafted for it. Anything missing from `ia.md` starts at `inbox`. Add your own
sites by hand. `routing.example.json` documents the whole schema, including the
order the tables are consulted in. Skip the file entirely and everything lands
in `inbox` — the rules are only a prior, and Sonnet still places each annotation
against `ia.md`.

## Driving the system from Hypothesis

Tag any annotation and within ~5 minutes each action tag produces its own
instruction file in `actions/` (tags combine — `hedge` + `cite` yields two
files). The full vocabulary is defined in `architecture/ia.md` (edit there;
Sonnet reads it live):

- **Prose & argument** — `revision`, `expansion`, `condense`, `restructure`,
  `hedge`, `reframe`, `exemplify`, `counter`, `define`
- **Research & evidence** — `cite`, `evidence`, `verify`, `question`,
  `synthesize` (draws on sibling annotations at the same node)
- **Development objects** — `bug`, `feature`, `a11y`
- **Status (no action file)** — `outstanding`, `resolved`

Untagged annotations are still classified into the IA with a one-sentence
"role" statement.

## Operations

```sh
# is the watcher actually running?
python3 scripts/doctor.py

# watch it work
tail -f logs/watcher.log

# run once by hand (or preview without writing)
python3 scripts/poll.py
python3 scripts/poll.py --dry-run

# install / pause / resume the watcher (see INSTALL.md for systemd and cron)
python3 scripts/install_agent.py --write
launchctl unload ~/Library/LaunchAgents/local.hypothesis-watcher.plist
launchctl load   ~/Library/LaunchAgents/local.hypothesis-watcher.plist

# full re-backfill + re-sort (rebuilds map from rules; Sonnet judgments are overwritten)
python3 scripts/fetch_annotations.py && python3 scripts/build_ia.py
```

Editing `architecture/ia.md` immediately changes how Sonnet classifies —
it is included in every classification prompt.

Both logs are self-limiting: a poll that finds either past 1 MB rewrites it in
place, keeping the last ~250 KB behind a `--- earlier entries trimmed ---`
marker. Nothing external rotates them, and 288 runs a day would otherwise grow
them without bound.

## Tests and lint

The suite mocks the Hypothesis API and the `claude` subprocess, so it never
spends API money, and `conftest.py` redirects every write path to a tmp dir so
runs never touch `logs/`, `data/`, or `actions/`. `pytest` and `ruff` are
dev-only dependencies (no runtime deps beyond the stdlib):

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install pytest ruff
pytest
ruff check .
```

GitHub Actions runs both on every push and pull request
(`.github/workflows/ci.yml`, Python 3.11 and 3.12). CI has neither
`config.json` nor `routing.json`; both fall back to their committed `.example`
so imports still resolve, and the routing tests supply fictional tables of their
own rather than asserting against anyone's real groups.

## Checking that the watcher is alive

An empty `watcher.log` is ambiguous: a quiet week and a watcher that never
starts look identical, because a job the scheduler cannot spawn writes nothing
at all. `scripts/doctor.py` checks the things whose absence is otherwise
invisible and exits non-zero if any of them is broken:

- the config keys `poll.py` needs (the token is never printed) and the `claude` binary
- a launchd/systemd unit for *this* checkout whose interpreter still exists —
  the one failure that kills the watcher silently, since launchd answers
  `last exit code = 78: EX_CONFIG`, runs nothing, and logs nothing
- the heartbeat: every completed poll stamps `data/health.json`, so a timestamp
  older than three intervals means no poll is happening. The same file records
  how many annotations took the rules fallback on the last run, which is how a
  live-but-degraded classifier shows up.

A run that does not complete says so rather than leaving the last good stamp in
place. The scheduler sends `SIGTERM` when the machine sleeps or the job is
unloaded, which can land in the middle of a classification that takes minutes;
that run logs where it stopped and records `status: interrupted`. An unhandled
exception records `status: error` with the traceback. Neither loses work — the
cursor only advances once an annotation is fully written, so the next run
re-fetches whatever was in flight — but `doctor.py` reports both as warnings
instead of a green heartbeat.

Classification is not free — one annotation is one `claude -p` call, on the
order of ten to twenty cents. Every run records what the CLI says it charged, per
annotation in `architecture/map.jsonl` and in the watcher log, and `doctor.py`
reports the lifetime total alongside the heartbeat. Annotations that took the
rules fallback cost nothing and record nothing.

One run classifies at most `max_per_run` annotations (default 25, `0` for no
limit). A larger backlog — a first run with an old `since`, a bulk re-tag — is
paced across successive runs instead of billed in one sitting; the log and the
heartbeat's `detail` say how many were deferred.

`max_daily_usd` caps what classification may cost per UTC day (`0`, the
default, for no ceiling; `config.example.json` sets 5). The count cap bounds
one run, but a queue that stays full all day would still add up. Once the day's
spend reaches the ceiling, polls stop classifying and the cursor holds, so the
waiting annotations are picked up after midnight UTC, none skipped. The
heartbeat reads `status: budget` and `doctor.py` warns until then. The check
runs before each call, so a day can overshoot by at most one classification.

```sh
python3 scripts/doctor.py
ok   config: watching acct:you@hypothes.is
ok   claude cli: /usr/local/bin/claude
ok   scheduler: local.hypothesis-watcher.plist runs /usr/bin/python3
ok   heartbeat: last poll 3 min ago, 0 processed, $4.31 spent on classification to date
```

## When classification stops working

Sonnet failures are non-fatal — the annotation still gets placed by the rules
and the record is marked `rules-fallback`. The watcher log names the cause. The
most common one is an expired login on the `claude` CLI, reported as
`claude cli is not authenticated (…)`; fix it by running `claude` and signing in
again. Auth failures are not retried, since a dead login will not heal between
attempts.

## Network faults

Polling rides out transient failures — DNS loss on a sleeping laptop, connection
resets, SSL EOF, read timeouts, and `429`/`5xx` from the API — with three
attempts and exponential backoff inside one five-minute interval. If they all
fail, the run logs a single line and exits cleanly rather than raising; the
message is written once per outage, not once per poll, and a recovery line
follows when the API answers again. Requests the API rejects (a `4xx`, such as
`400` for an unreadable `since`) are not retried: the log line says a retry will
not fix them and points at `config.json` instead.

## License

MIT — see [LICENSE](LICENSE).
