# Hypothesis Annotation System

Pulls every Hypothesis annotation by `zachmuhlbauer`, sorts it into an
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
`revision` to an old annotation also triggers the routine**.

## Layout

| Path | Purpose |
|---|---|
| `config.json` | API token, user, model, backfill start date (chmod 600) |
| `data/annotations.jsonl` | Raw two-year pull (2024-07-15 →) |
| `data/cursor.json`, `data/seen.json` | Watcher state |
| `architecture/ia.md` | The taxonomy — hand-editable; Sonnet reads it on every classification |
| `architecture/map.jsonl` | One record per annotation: node, workflow, role, quote, note, link |
| `architecture/overview.md` | Generated per-node counts |
| `architecture/emergent-nodes.md` | Sub-nodes Sonnet proposed; review and fold into ia.md |
| `actions/` | Generated instruction files for tagged editorial directives |
| `scripts/fetch_annotations.py` | Full re-pull (backfill) |
| `scripts/build_ia.py` | Rule-based initial sort of the backfill |
| `scripts/poll.py` | The watcher + Sonnet 5 classifier |
| `launchd/…watcher.plist` | Runs poll.py every 5 min (installed in ~/Library/LaunchAgents) |

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
# watch it work
tail -f logs/watcher.log

# run once by hand (or preview without writing)
python3 scripts/poll.py
python3 scripts/poll.py --dry-run

# pause / resume the watcher
launchctl unload ~/Library/LaunchAgents/com.zachmuhlbauer.hypothesis-watcher.plist
launchctl load   ~/Library/LaunchAgents/com.zachmuhlbauer.hypothesis-watcher.plist

# full re-backfill + re-sort (rebuilds map from rules; Sonnet judgments are overwritten)
python3 scripts/fetch_annotations.py && python3 scripts/build_ia.py
```

Editing `architecture/ia.md` immediately changes how Sonnet classifies —
it is included in every classification prompt.
