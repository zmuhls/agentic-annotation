# Installing the watcher

From a fresh clone to an annotation being classified within five minutes.
Nothing below assumes the maintainer's machine: every path comes from the
checkout you run the commands in.

## 1. Requirements

- **Python 3.11+** — the runtime is stdlib only, no `pip install` needed to run it.
- **The `claude` CLI**, signed in — the classifier shells out to
  `claude -p --model claude-sonnet-5`. Install it, run `claude` once, and sign
  in. Without it the watcher still works, but every annotation is placed by the
  rules and recorded as `rules-fallback`.
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
| `since` | how far back the first backfill reaches (ISO 8601) |
| `model` | `claude-sonnet-5` unless you have a reason to change it |
| `claude_bin` | optional — an explicit path to the `claude` binary |

Then draft your placement tables from your own Hypothesis groups:

```sh
python3 scripts/bootstrap_routing.py --write
```

That writes `routing.json` naming every group you belong to and pointing each at
`inbox`. Edit those to node ids from `architecture/ia.md` and add the domains you
annotate; `routing.example.json` documents the whole schema and the order the
tables are consulted in. Both `config.json` and `routing.json` are gitignored.

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

## 6. Confirm it is running

```sh
tail -f logs/watcher.log
```

Annotate something, tag it `revision`, and within about five minutes you should
see the annotation placed and an instruction file appear under `actions/`. Both
logs are trimmed to their last ~250 KB automatically once they pass 1 MB.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `claude cli is not authenticated (…)` in `logs/watcher.log` | The CLI login expired. Run `claude`, sign in. Placement falls back to the rules until you do. |
| Everything lands in `inbox` | `routing.json` is missing or its nodes are still the bootstrap defaults. |
| `hypothesis api unreachable (…)` | Transient — a sleeping laptop or dropped wifi. Retried with backoff, logged once per outage, cleared on recovery. |
| `401` from the API | Bad or revoked token in `config.json`. Not retried, by design. |
| No log entries at all | The unit is not loaded. Check `launchctl list` / `systemctl --user list-timers`. |
| Nothing processes but annotations exist | `data/cursor.json` is ahead of them. Rewind `search_after` to an earlier timestamp. |
