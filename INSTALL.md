# Installing the watcher

From a fresh clone to an annotation being classified within five minutes.
Nothing below assumes the maintainer's machine: every path comes from the
checkout you run the commands in.

## 1. Requirements

- **Python 3.9+** — macOS's own `/usr/bin/python3` (3.9) is enough, and CI
  tests 3.9, 3.11, and 3.12. The runtime is stdlib only, no `pip install`
  needed to run it.
- **The `claude` CLI**, signed in — the classifier shells out to
  `claude -p --model claude-sonnet-5`. Install it, run `claude` once, and sign
  in. Missing or signed out, it holds new annotations in the queue until it
  answers again. That stored login has to keep refreshing itself and can
  lapse; for a background job, `claude setup-token` prints a long-lived token
  you can hand the watcher through `claude_env` (below) instead. To run
  without the CLI, set `"model": "rules"` in `config.json`:
  every annotation is then placed by `routing.json` alone, recorded as
  `rules`, at no cost.
- **A Hypothesis developer token** — <https://hypothes.is/account/developer>.

Each classification costs roughly $0.10 of API usage, and the watcher only calls
the model when an annotation is new or edited.

## 2. Configure

```sh
git clone https://github.com/zmuhls/agentic-annotation.git
cd agentic-annotation

cp config.example.json config.json && chmod 600 config.json
```

Fill in `config.json`:

| Key | Value |
|---|---|
| `api_token` | your Hypothesis developer token |
| `user` | `acct:yourname@hypothes.is` |
| `owner` | how the prompt should name whose knowledge system this is |
| `since` | where the backfill and the watcher's first poll start (ISO 8601). Without it the backfill pulls your whole history and the watcher classifies only what you annotate after its first run |
| `model` | `claude-sonnet-5` unless you have a reason to change it; `rules` runs without the `claude` CLI and places by `routing.json` alone |
| `max_per_run` | most annotations one poll classifies (default 25; `0` = no limit) |
| `max_daily_usd` | dollar ceiling on classification per UTC day (default `0` = no limit; the example sets 5) |
| `claude_bin` | optional — an explicit path to the `claude` binary; otherwise `PATH`, then `~/.local/bin/claude` |
| `claude_env` | optional — variables for the `claude` CLI, which launchd, systemd, and cron never pass from your shell. `{"CLAUDE_CODE_OAUTH_TOKEN": "…"}` with the token `claude setup-token` prints (needs a Claude subscription) gives the watcher a login of its own that outlasts the interactive one; `ANTHROPIC_API_KEY` works too and bills that API account. Either is a secret, like `api_token` |

Then draft your taxonomy and placement tables from your own annotation history:

```sh
python3 scripts/bootstrap.py                   # preview: each group and busy domain → its node
python3 scripts/bootstrap.py --write --force   # writes architecture/ia.md and routing.json
```

That one command runs the two drafters described below, in order, from a single
fetch of your groups and recent annotations. It reads the routing's node ids off
the `ia.md` it is drafting rather than the one on disk, so the two files agree
even in the preview, and it writes both or neither. Run the two scripts on their
own for a full-text preview of either file, or to redraft one after editing the
other.

**The taxonomy (`bootstrap_ia.py`).** `architecture/ia.md` ships with the
maintainer's taxonomy, and it is the file the classifier reads on every poll —
leaving it in place would sort your annotations into someone else's projects.
The script replaces its nodes section with one top-level node per group you
belong to, each group's busiest domains as children, your public-layer reading
under `reading`, and `inbox`. The action-tag vocabulary below it is the same for
everyone (`poll.py` and `build_ia.py` implement it), so it carries over
untouched. Then edit: the node descriptions are what the model reasons over, and
the generated ones are placeholders.

**The placement tables (`bootstrap_routing.py --write`).** It writes
`routing.json` naming every group you belong to and pointing each at the node
`bootstrap_ia.py` drafted for it: the group's `/general` node, and for its
busiest domains the matching child node. Public-layer domains go under
`reading`. It names only node ids that the `ia.md` on disk defines, so run it
after `bootstrap_ia.py`. Anything that `ia.md` lacks (a group you pruned, or
every group if you skipped the step above) starts at `inbox`, and the script
counts those for you. Then add your own sites under `artifact_domains`;
`routing.example.json` documents the whole schema and the order the tables are
consulted in. Both `config.json` and `routing.json` are gitignored.

## 3. Backfill and sort

```sh
python3 scripts/fetch_annotations.py   # pulls your annotations since `since`
python3 scripts/build_ia.py            # rule-based first sort into architecture/
```

Read `architecture/overview.md` afterwards. Anything landing in `inbox` in bulk
usually means a group or domain is missing from `routing.json`.

## 4. Check it by hand before scheduling it

```sh
python3 scripts/poll.py --dry-run      # prints what it would do, writes nothing
```

## 5. Schedule it

`scripts/install_agent.py` generates the scheduler unit from this checkout — its
absolute path, the interpreter you invoke it with, and a label you choose. Print
it first, install it with `--write`.

### macOS (launchd)

```sh
python3 scripts/install_agent.py                       # inspect the plist
python3 scripts/install_agent.py --write               # ~/Library/LaunchAgents/…
launchctl load ~/Library/LaunchAgents/local.hypothesis-watcher.plist
```

Verify with `launchctl list | grep hypothesis` — the second column is the last
exit status and should be `0`. Pause with `launchctl unload <same path>`.

macOS may prompt the first time the agent reaches the network or reads a folder
under Documents/Desktop; approve it, or the polls fail silently.

### Linux (systemd user timer)

```sh
python3 scripts/install_agent.py --target systemd --write
systemctl --user daemon-reload
systemctl --user enable --now local.hypothesis-watcher.timer
systemctl --user list-timers local.hypothesis-watcher.timer
```

Run `loginctl enable-linger $USER` if you want it polling while you are not
logged in. Logs: `journalctl --user -u local.hypothesis-watcher.service`, plus
the same `logs/launchd.log` the macOS agent writes.

### Anywhere else (cron)

```sh
python3 scripts/install_agent.py --target cron     # prints one crontab line
crontab -e                                         # paste it in yourself
```

Cron runs with a minimal `PATH`, so keep the absolute interpreter path the
generated line uses, and set `claude_bin` in `config.json` if `claude` is not
found.

Useful flags for all three: `--interval <seconds>` (default 300), `--label
<name>`, `--python <interpreter>`, `--force` to overwrite an installed unit.

Pick an interpreter that will still be there next month. The unit records an
absolute path, and `--write` refuses one that does not exist today, because a
scheduler cannot report a program it cannot spawn: launchd just records
`last exit code = 78: EX_CONFIG` and writes nothing to the log. A system
`python3` outlives a toolchain you might uninstall. (`--allow-missing-python`
exists only for generating a unit meant for another machine.)

## 6. Confirm it is running

```sh
python3 scripts/doctor.py     # config, token, claude cli, scheduler unit, heartbeat
tail -f logs/watcher.log
```

`doctor.py` exits non-zero when something is broken, so it also works as a
periodic check of its own. It is the fastest way to tell a quiet week from a
dead watcher: every completed poll stamps `data/health.json`, and a heartbeat
older than three intervals means no poll is happening — which an empty log
cannot tell you.

Annotate something, tag it `revision`, and within about five minutes you should
see the annotation placed and an instruction file appear under `actions/`. Both
logs are trimmed to their last ~250 KB automatically once they pass 1 MB.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `claude cli is not authenticated (…)` in `logs/watcher.log` | The CLI login expired. Run `claude`, sign in, or set a long-lived token in `claude_env` so it stops lapsing; if the line names a `claude_env` credential, that credential was refused, so replace it. Until you do, new annotations wait in the queue (heartbeat `status: auth`, `doctor.py` fails the `claude cli` check), and the first poll after you sign in classifies them. The line is logged once per lapse. |
| `claude cli could not start (…)` in `logs/watcher.log` | Nothing executable at the path the watcher tried, which the line names; an update or reinstall can move the CLI. Install it, or point `claude_bin` in `config.json` at it. Until then new annotations wait in the queue (heartbeat `status: no-cli`, `doctor.py` fails the `claude cli` check). Set `"model": "rules"` to run without it. |
| Everything lands in `inbox` | `routing.json` is missing, or it was drafted before `bootstrap_ia.py` rewrote `ia.md`. Re-run `bootstrap_routing.py --write --force`, or `bootstrap.py --write --force` to redraft both. |
| `hypothesis api unreachable (…)` | Transient — a sleeping laptop or dropped wifi. Retried with backoff, logged once per outage, cleared on recovery. |
| `hypothesis api rejected the request (…)` | A `4xx` from the API: the request will fail the same way on every poll until `config.json` changes. Not retried, by design. The text in parentheses is the API's own reason. |
| Private-group annotations never arrive, and nothing errors | The token in `config.json` is wrong or revoked. `/api/search` does not reject a token it does not recognize. It answers as an anonymous user and returns public annotations only. `doctor.py` asks `/api/profile`, which does tell, and fails on a token the API does not know. Generate a new token at hypothes.is/account/developer. |
| `400 Bad Request: search_after must be a parsable date…` | `since` in `config.json` is not a date the API can read, and no cursor exists yet. Set it to ISO 8601 (`2024-07-15T00:00:00+00:00`) or remove it; `doctor.py` flags this. |
| No log entries at all | Run `python3 scripts/doctor.py`. Either the unit is not loaded, or it names an interpreter that no longer exists — launchd reports that as `78: EX_CONFIG` in `launchctl list` and logs nothing. Re-run `install_agent.py --write --force` with a present interpreter and reload the unit. |
| `doctor.py` says the heartbeat is stale | No poll has completed recently, whatever the log says. Check the unit first, then run `python3 scripts/poll.py` by hand and read the error. |
| Nothing processes but annotations exist | `data/cursor.json` is ahead of them. Rewind `search_after` to an earlier timestamp. |
