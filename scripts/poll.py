#!/usr/bin/env python3
"""Incremental Hypothesis watcher + Claude Sonnet 5 classifier.

Hypothesis has no webhooks, so this polls /api/search on a cursor over the
`updated` timestamp (new annotations AND tag edits to old ones re-trigger).
Each new/updated annotation is sent to Claude Sonnet 5 (headless `claude -p`),
which places it in the information architecture (architecture/ia.md) and,
when the annotation carries a revision / expansion / condense tag, writes
concrete instructions for the target artifact into actions/.

Run every 5 minutes by the scheduler unit that scripts/install_agent.py writes
(launchd on macOS, a systemd user timer on Linux).
Manual run: python3 scripts/poll.py [--dry-run]
"""

import fcntl
import json
import shutil
import signal
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from appconfig import load_config  # noqa: E402
from bootstrap_ia import first_child, nodes_of  # noqa: E402
from build_ia import (  # noqa: E402
    actions_for,
    group_name_for,
    node_for,
    quote_of,
    record_for,
    title_of,
    write_overview,
)

CONFIG = load_config()
API = "https://api.hypothes.is/api"
MODEL = CONFIG.get("model", "claude-sonnet-5")
# How the classifier prompt names whose knowledge system this is. Keeping the
# owner in config rather than in the prompt string is what lets someone else
# adopt the repo without editing code.
OWNER = CONFIG.get("owner", "this Hypothesis knowledge system")
# Most annotations one poll will classify. Each is a real billed call (~$0.19
# measured) run serially under the poll lock, so an unbounded batch — a first
# run with an old `since`, a bulk re-tag — is both an open-ended bill and a
# long window for a sleep SIGTERM. The rest wait for the next run; 0 disables.
MAX_PER_RUN = int(CONFIG.get("max_per_run", 25) or 0)
# Dollar ceiling on classification per UTC day. The count cap above bounds one
# run, but 288 runs a day each within their cap still add up without limit — a
# re-tag loop or an import script can keep the queue full all day. Once the
# day's spend reaches this, polls stop classifying (the cursor holds, nothing
# is skipped) until the date rolls over. 0 disables it.
MAX_DAILY_USD = float(CONFIG.get("max_daily_usd", 0) or 0)

CURSOR_FILE = ROOT / "data" / "cursor.json"
SEEN_FILE = ROOT / "data" / "seen.json"
MAP_FILE = ROOT / "architecture" / "map.jsonl"
IA_FILE = ROOT / "architecture" / "ia.md"
EMERGENT_FILE = ROOT / "architecture" / "emergent-nodes.md"
ACTIONS_DIR = ROOT / "actions"
LOG_FILE = ROOT / "logs" / "watcher.log"
STDOUT_LOG = ROOT / "logs" / "launchd.log"
LOCK_FILE = ROOT / "data" / ".poll.lock"
NETFAIL_FILE = ROOT / "data" / ".netfail"
HEALTH_FILE = ROOT / "data" / "health.json"

# Nothing ever pruned the logs: 288 runs a day append forever, and one bad week
# of tracebacks had already put launchd.log past 200 KB of text no one will read
# again. Keep a working tail rather than the whole history.
LOG_MAX_BYTES = 1_000_000
LOG_KEEP_BYTES = 250_000

# HTTP statuses worth a retry; anything else (401 bad token, 400 bad query) is
# a real fault the caller should see immediately.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a") as f:
        f.write(f"[{stamp}] {msg}\n")
    # flush: stdout is the scheduler's log file, so it is block-buffered, and a
    # run killed mid-classification otherwise loses the very lines that would
    # have explained the kill.
    print(msg, flush=True)


def trim_log(path, max_bytes=LOG_MAX_BYTES, keep_bytes=LOG_KEEP_BYTES):
    """Shrink an oversized log in place, keeping its last whole lines.

    In place, not renamed: the scheduler redirects this process's stdout into
    launchd.log with an append-mode descriptor it owns, and renaming the file
    would leave that descriptor writing to an inode nobody reads. Rewriting the
    same inode just moves EOF back — the next append lands after the tail.
    """
    try:
        if not path.exists() or path.stat().st_size <= max_bytes:
            return False
        with path.open("rb") as f:
            f.seek(-keep_bytes, 2)
            tail = f.read()
    except OSError:
        return False  # a log we cannot prune is not worth failing a poll over
    tail = tail.split(b"\n", 1)[-1]  # drop the partial first line
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    header = f"[{stamp}] --- earlier entries trimmed (log exceeded {max_bytes} bytes) ---\n"
    with path.open("wb") as f:
        f.write(header.encode() + tail)
    return True


def search(params, attempts=3, backoff=5):
    """GET /api/search, riding out transient network faults.

    A laptop that sleeps, drops wifi, or hits an api hiccup produced the bulk of
    this watcher's failures (DNS, connection reset, ssl eof, read timeout — all
    OSError subclasses, as is urllib's URLError). Retry those a couple of times
    within one launchd interval; let genuine faults (401, 400) raise at once.
    """
    url = f"{API}/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {CONFIG['api_token']}"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUSES or attempt == attempts - 1:
                raise
        except OSError:
            if attempt == attempts - 1:
                raise
        time.sleep(backoff * (2**attempt))


def api_reason(err):
    """`err`'s status, plus the reason /api/search put in the error body.

    A bare "400 Bad Request" says nothing about which value the api refused,
    but the body names it — an unreadable `since`, for one, comes back as
    "search_after must be a parsable date..." (probed live). Bodies that are
    missing or not JSON leave just the status.
    """
    status = f"{err.code} {err.reason}"
    try:
        reason = json.loads(err.read().decode()).get("reason") or ""
        reason = " ".join(reason.lstrip(": ").split())
    except Exception:  # an HTTPError with no body raises KeyError from read() on 3.9
        return status
    return f"{status}: {reason}" if reason else status


def ms_before(stamp):
    """The `search_after` that re-reads the whole millisecond `stamp` falls in.

    `updated` carries microseconds, but /api/search truncates `search_after` to
    milliseconds and returns only rows strictly after that (probed live). A
    search from the cursor itself therefore drops every other annotation in the
    cursor's millisecond, so a batch cap, a spend stop, or a page boundary that
    landed inside one stranded the rest of it. Starting a millisecond earlier
    re-reads it, and `seen` drops the rows already done. A stamp that does not
    parse (no cursor yet, an odd `since`) passes through unchanged.
    """
    try:
        t = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp
    t = t.replace(microsecond=t.microsecond // 1000 * 1000) - timedelta(milliseconds=1)
    return t.isoformat(timespec="microseconds")


def fetch_new(cursor, page_size=200, key="updated"):
    """Annotations whose `key` stamp is in the cursor's millisecond or later, oldest first.

    After a full page the next one restarts a millisecond before its last row
    (see ms_before), and the overlap is dropped by id. Only a full page that
    brings nothing new — more than `page_size` rows in one millisecond — falls
    back to the strict cursor, the one way past it. The watcher pages on
    `updated`; the backfill (fetch_annotations.py) pages on `created`.
    """
    rows, ids, search_after = [], set(), ms_before(cursor)
    while True:
        page = search(
            {
                "user": CONFIG["user"],
                "sort": key,
                "order": "asc",
                "search_after": search_after,
                "limit": page_size,
            }
        ).get("rows", [])
        batch = [r for r in page if r["id"] not in ids]
        rows.extend(batch)
        ids.update(r["id"] for r in batch)
        if len(page) < page_size:
            return rows
        last = page[-1][key]
        search_after = ms_before(last) if batch else last


def claude_bin():
    return (
        CONFIG.get("claude_bin")
        or shutil.which("claude")
        or str(Path.home() / ".local" / "bin" / "claude")
    )


def siblings_at(node, exclude_id, limit=6):
    """Compact context: recent annotations already mapped to the same node."""
    if not MAP_FILE.exists():
        return []
    records = [json.loads(line) for line in MAP_FILE.open()]
    sibs = [r for r in records if r["node"] == node and r["id"] != exclude_id]
    sibs.sort(key=lambda r: r.get("created", ""), reverse=True)
    return [
        {
            "title": r.get("title") or r.get("uri", ""),
            "gist": (r.get("role") or r.get("note") or r.get("quote") or "")[:120],
        }
        for r in sibs[:limit]
    ]


def new_node_example(ia):
    """A deeper-child example built from a node in the reader's own ia.md.

    A fixed example here named one author's node on every call, and in anyone
    else's taxonomy that node does not exist. bootstrap_ia.draft rewrites the
    matching example in ia.md's preamble for the same reason.
    """
    child = first_child(nodes_of(ia))
    return f"{child}/<child>" if child else "<existing-node>/<child>"


def classify_prompt(ann):
    ia = IA_FILE.read_text()
    group = group_name_for(ann)
    predicted = node_for(ann)
    payload = {
        "uri": ann.get("uri", ""),
        "title": title_of(ann),
        "group": group,
        "tags": ann.get("tags", []),
        "quoted_passage": quote_of(ann)[:600],
        "annotation_note": (ann.get("text") or "")[:2000],
        "created": ann.get("created", ""),
        "is_reply": bool(ann.get("references")),
    }
    action_tags = actions_for(ann.get("tags", []))
    return f"""You are the annotation librarian for {OWNER}. The information architecture is below, followed by one new annotation.

<information_architecture>
{ia}
</information_architecture>

<annotation>
{json.dumps(payload, indent=2)}
</annotation>

<neighbors note="recent annotations already living at the rule-predicted node '{predicted}'">
{json.dumps(siblings_at(predicted, ann.get("id")), indent=2)}
</neighbors>

Do three things:

1. Assign the annotation to exactly one node. Prefer an existing node id from the architecture. You may propose one new child under an existing node (e.g. "{new_node_example(ia)}") when a cluster clearly deserves it; set "new_node" true in that case. Use "inbox" only as a last resort.

2. In one sentence, state the annotation's role within the broader architecture — what it contributes to or connects with at that node.

3. This annotation carries these action tags: {json.dumps(action_tags)}. For EACH action tag, produce one action object honoring that tag's directive as defined in the Action vocabulary section of the architecture. Instructions must be concrete and executable — anchored to the quoted passage, faithful to the note's intent, specific about what to do (for `synthesize`, draw on the neighbors above). If the list of action tags is empty, "actions" is an empty list.

Respond with ONLY a JSON object (no markdown fences, no commentary):
{{"node": "<node-id>", "new_node": false, "role": "<one sentence>", "actions": [{{"type": "<the action tag>", "artifact": "<uri>", "anchor": "<quoted passage or location>", "instructions": "<what to do>"}}]}}"""


def cli_error_text(proc):
    """Why the claude CLI failed.

    It reports API and auth failures as a JSON envelope on *stdout* and leaves
    stderr empty, so `proc.stderr` alone logs a bare "claude exited 1: " that
    says nothing — which is exactly what the watcher log held for every past
    failure. Prefer stderr when it has content, else dig the message out of the
    envelope.
    """
    if (proc.stderr or "").strip():
        return proc.stderr.strip()[:400]
    try:
        payload = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        return (proc.stdout or "").strip()[:400] or "no output"
    messages = payload if isinstance(payload, list) else [payload]
    for msg in reversed(messages):
        if isinstance(msg, dict) and (msg.get("is_error") or msg.get("error")):
            detail = msg.get("result") or msg.get("error")
            if detail:
                return str(detail)[:400]
    return (proc.stdout or "").strip()[:400] or "no output"


# A dead login does not heal in the 30s between attempts, and every retry burns
# another poll interval — say so on the first failure instead.
AUTH_MARKERS = ("authenticate", "oauth", "unauthorized", "invalid api key", "please run /login")


def call_sonnet(prompt, attempts=2, meta=None):
    """Classify one annotation, optionally reporting what the call cost.

    `meta`, when given, is filled with the CLI's own accounting (`cost_usd`)
    rather than returned alongside the classification: the return value stays
    the model's JSON, which is what every caller actually wants, and telemetry
    a caller does not ask for costs it nothing.
    """
    proc, detail = None, ""
    for attempt in range(attempts):
        proc = subprocess.run(
            [claude_bin(), "-p", "--model", MODEL, "--output-format", "json"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode == 0:
            break
        detail = cli_error_text(proc)
        if any(m in detail.lower() for m in AUTH_MARKERS):
            raise RuntimeError(
                f"claude cli is not authenticated ({detail}) — run `claude` "
                "and sign in; classification is falling back to rules until then"
            )
        if attempt < attempts - 1:
            time.sleep(30)  # transient API outages are common enough to ride out
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {detail}")
    try:
        wrapper = json.loads(proc.stdout)
    except json.JSONDecodeError:
        wrapper = None
    envelope = None
    if isinstance(wrapper, dict):
        envelope = wrapper
    elif isinstance(wrapper, list):
        # some CLI versions emit a list of message objects ending in a result
        envelope = next(
            (m for m in reversed(wrapper) if isinstance(m, dict) and m.get("type") == "result"), {}
        )
    result = proc.stdout if envelope is None else envelope.get("result", "")
    if meta is not None and isinstance(envelope, dict):
        meta["cost_usd"] = envelope.get("total_cost_usd")
    start, end = result.find("{"), result.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON in model output: {result[:200]}")
    return json.loads(result[start : end + 1])


def upsert_map(record):
    records = []
    if MAP_FILE.exists():
        records = [json.loads(line) for line in MAP_FILE.open()]
    records = [r for r in records if r["id"] != record["id"]] + [record]
    with MAP_FILE.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return records


def write_action_file(ann, action):
    ACTIONS_DIR.mkdir(exist_ok=True)
    date = ann.get("updated", "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = ACTIONS_DIR / f"{date}-{action['type']}-{ann['id']}.md"
    title = title_of(ann)
    path.write_text(f"""# {action["type"].capitalize()}: {title or ann.get("uri", "")}

- **artifact**: {action.get("artifact", ann.get("uri", ""))}
- **annotation**: {ann.get("links", {}).get("incontext", "")}
- **tagged**: {", ".join(ann.get("tags", []))}
- **created**: {ann.get("created", "")}

## Anchor

> {action.get("anchor", quote_of(ann))}

## Annotation note

{ann.get("text") or "(no note)"}

## Instructions

{action.get("instructions", "")}
""")
    return path


def note_emergent(node, role, ann):
    if not EMERGENT_FILE.exists():
        EMERGENT_FILE.write_text(
            "# Emergent nodes proposed by Sonnet (review, then fold into ia.md)\n\n"
        )
    with EMERGENT_FILE.open("a") as f:
        f.write(f"- `{node}` — {role} (from {ann.get('links', {}).get('incontext', ann['id'])})\n")


def note_network_failure(msg):
    """Log an outage once, not once per five-minute poll.

    A wifi drop otherwise writes the same line 288 times a day into the log the
    health review reads. Remember the last message; only log when it changes.
    """
    if not NETFAIL_FILE.exists() or NETFAIL_FILE.read_text() != msg:
        log(msg)
        NETFAIL_FILE.parent.mkdir(parents=True, exist_ok=True)
        NETFAIL_FILE.write_text(msg)


def record_health(status, processed=0, fallbacks=0, detail="", cost_usd=0.0):
    """Stamp proof that a poll actually ran, for scripts/doctor.py to read.

    The watcher once stopped for four days in silence: its scheduler unit named
    an interpreter that had since been uninstalled, so the process never
    started and never logged. An empty log looks exactly like a quiet week —
    a file whose timestamp stops advancing does not.
    """
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Carry the lifetime spend forward. Each classification is a real ~$0.10
    # API call, and a per-run figure alone never answers the question anyone
    # actually asks — what has this watcher cost me? The file is rewritten on
    # every poll, so the running total has to be read back first.
    spent = 0.0
    if HEALTH_FILE.exists():
        try:
            spent = float(json.loads(HEALTH_FILE.read_text()).get("cost_usd_total") or 0.0)
        except (OSError, ValueError, TypeError):
            spent = 0.0  # a corrupt stamp restarts the tally, never fails a poll
    now = datetime.now(timezone.utc)
    HEALTH_FILE.write_text(
        json.dumps(
            {
                "last_run": now.isoformat(timespec="seconds"),
                "status": status,
                "processed": processed,
                "fallbacks": fallbacks,
                "cost_usd": round(cost_usd, 4),
                "cost_usd_total": round(spent + cost_usd, 4),
                "cost_day": now.date().isoformat(),
                "cost_usd_today": round(spent_today() + cost_usd, 4),
                "detail": detail,
            },
            indent=2,
        )
        + "\n"
    )


def spent_today():
    """What classification has cost so far this UTC day, per the heartbeat.

    A stamp from an earlier day, or none at all, means nothing spent yet.
    """
    try:
        health = json.loads(HEALTH_FILE.read_text())
    except (OSError, ValueError):
        return 0.0
    if health.get("cost_day") != datetime.now(timezone.utc).date().isoformat():
        return 0.0
    try:
        return float(health.get("cost_usd_today") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _interrupt_handler(dry_run):
    """Say where a cut-short run stopped, instead of vanishing mid-classification.

    launchd sends SIGTERM when the machine sleeps or the job is unloaded, and a
    single `claude -p` call can be in flight for minutes. Python's default
    handler kills the process outright: on 2026-09-21 a run logged "processing 1
    new/updated annotation(s)" and then nothing at all — no traceback, no health
    stamp, and not even that line in the scheduler log. Nothing was lost (the
    cursor only advances per finished annotation, so the next run re-fetches),
    but the silence cost an hour of forensics to rule out a real fault.
    """

    def handler(signum, _frame):
        name = signal.Signals(signum).name
        log(
            f"poll interrupted by {name} mid-run; no state written, "
            "the next run picks up from the same cursor"
        )
        if not dry_run:
            record_health("interrupted", detail=f"run cut short by {name}")
        sys.exit(128 + signum)

    return handler


def install_interrupt_handlers(dry_run):
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _interrupt_handler(dry_run))


def clear_network_failure():
    if NETFAIL_FILE.exists():
        NETFAIL_FILE.unlink()
        log("hypothesis api reachable again")


def process(ann, dry_run=False):
    wanted = actions_for(ann.get("tags", []))
    record = record_for(ann)  # rules-based baseline record
    actions = []
    meta = {}
    try:
        result = call_sonnet(classify_prompt(ann), meta=meta)
        record["node"] = result.get("node") or record["node"]
        record["role"] = result.get("role", "")
        record["classified_by"] = MODEL
        if meta.get("cost_usd") is not None:
            record["cost_usd"] = round(meta["cost_usd"], 4)
        actions = result.get("actions") or []
        if isinstance(actions, dict):  # tolerate a bare single object
            actions = [actions]
        legacy = result.get("action")  # pre-vocabulary contract
        if legacy and not actions:
            actions = [legacy]
        if result.get("new_node") and not dry_run:
            note_emergent(record["node"], record.get("role", ""), ann)
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        where = f" at {tb[-1].filename.split('/')[-1]}:{tb[-1].lineno}" if tb else ""
        log(
            f"  sonnet failed for {ann['id']}: {type(e).__name__}: {e}{where}"
            "; falling back to rules"
        )
        record["classified_by"] = "rules-fallback"
    # every tagged action produces a file: stub any the model missed
    produced = {a.get("type") for a in actions}
    for tag in wanted:
        if tag not in produced:
            actions.append(
                {
                    "type": tag,
                    "artifact": ann.get("uri", ""),
                    "anchor": quote_of(ann),
                    "instructions": "(model produced no instructions — act on the annotation note directly)",
                }
            )
    actions = [a for a in actions if a.get("type") in wanted]  # tags drive files
    if dry_run:
        print(json.dumps({**record, "pending_actions": actions}, indent=2))
        return record
    upsert_map(record)
    for action in actions:
        path = write_action_file(ann, action)
        log(f"  action file: {path.name}")
    tags_note = f" [{','.join(wanted)}]" if wanted else ""
    cost_note = f" ${record['cost_usd']:.4f}" if record.get("cost_usd") else ""
    log(f"  {ann['id']} -> {record['node']}{tags_note}{cost_note}")
    return record


def main():
    dry_run = "--dry-run" in sys.argv
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock = LOCK_FILE.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # previous run still going
    install_interrupt_handlers(dry_run)
    try:
        poll_once(dry_run)
    except Exception as e:
        # Anything unhandled below (a write that fails, malformed map.jsonl)
        # used to leave only a traceback in the scheduler log while
        # data/health.json still read "ok" from the last good run — the exact
        # silence doctor.py exists to break.
        log(f"poll failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        if not dry_run:
            record_health("error", detail=f"{type(e).__name__}: {e}"[:200])
        sys.exit(1)


def start_cursor(dry_run):
    """Where a poll with no saved cursor starts: `since`, or else this moment.

    With neither, /api/search was asked for search_after=None, which it answers
    400 (probed live), so a config without `since` failed every run for good.
    A missing `since` now means "watch from the first run on": classification is
    billed, so the watcher never reaches into history unasked (the backfill does
    that, for free). The moment is saved at once, or each idle run would restart
    from its own now and drop whatever arrived between polls.
    """
    since = CONFIG.get("since")
    if since:
        return since
    now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    if not dry_run:
        CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        CURSOR_FILE.write_text(json.dumps({"search_after": now}))
        log("no `since` in config.json; watching annotations made from now on")
    return now


def poll_once(dry_run):
    for path in (LOG_FILE, STDOUT_LOG):
        trim_log(path)

    cursor = (
        json.loads(CURSOR_FILE.read_text())["search_after"]
        if CURSOR_FILE.exists()
        else start_cursor(dry_run)
    )
    seen = json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else {}

    try:
        anns = fetch_new(cursor)
    except urllib.error.HTTPError as e:  # a URLError/OSError subclass — catch first
        reason = api_reason(e)
        if e.code in RETRY_STATUSES:
            note_network_failure(f"hypothesis api returned {reason}; retrying next run")
        else:
            # search() declined to retry this: a 4xx such as an unreadable `since`
            # is refused the same way every run until config.json changes, so
            # promising a retry told adopters to wait for a fix that never comes.
            note_network_failure(
                f"hypothesis api rejected the request ({reason}); a retry "
                "will not fix this — check config.json or run "
                "scripts/doctor.py"
            )
        if not dry_run:
            record_health("api-error", detail=reason)
        return
    except OSError as e:
        note_network_failure(f"hypothesis api unreachable ({e}); retrying next run")
        if not dry_run:
            record_health("api-unreachable", detail=str(e))
        return
    clear_network_failure()

    fresh = [a for a in anns if seen.get(a["id"]) != a["updated"]]
    if not fresh:
        if not dry_run:
            record_health("ok")
        return
    budget_left = MAX_DAILY_USD - spent_today() if MAX_DAILY_USD > 0 else None
    if budget_left is not None and budget_left <= 0:
        # The run that hit the ceiling already logged it; the ones after it
        # classify nothing and say so in the heartbeat, not in 288 log lines.
        if not dry_run:
            record_health(
                "budget", detail=f"daily ceiling ${MAX_DAILY_USD:.2f} reached; {len(fresh)} waiting"
            )
        return
    fresh, deferred = cap_batch(fresh, MAX_PER_RUN)
    log(
        f"processing {len(fresh)} new/updated annotation(s) with {MODEL}"
        + (f"; {deferred} deferred to the next run (max_per_run={MAX_PER_RUN})" if deferred else "")
    )
    fallbacks, spend, done = 0, 0.0, 0
    for ann in fresh:
        # Checked before each call, since a call's price is known only after it.
        if budget_left is not None and spend >= budget_left:
            break
        record = process(ann, dry_run=dry_run)
        done += 1
        fallbacks += record.get("classified_by") == "rules-fallback"
        spend += record.get("cost_usd") or 0.0
        if not dry_run:
            seen[ann["id"]] = ann["updated"]
            SEEN_FILE.write_text(json.dumps(seen))
            CURSOR_FILE.write_text(json.dumps({"search_after": ann["updated"]}))
    held = len(fresh) - done
    if held:
        log(
            f"daily spend ceiling reached (${MAX_DAILY_USD:.2f}); "
            f"{held} annotation(s) wait for tomorrow (UTC)"
        )
    if not dry_run:
        if MAP_FILE.exists():
            write_overview([json.loads(line) for line in MAP_FILE.open()])
        waiting = deferred + held
        if held:
            record_health(
                "budget",
                processed=done,
                fallbacks=fallbacks,
                cost_usd=spend,
                detail=f"daily ceiling ${MAX_DAILY_USD:.2f} reached; {waiting} waiting",
            )
        else:
            record_health(
                "ok",
                processed=done,
                fallbacks=fallbacks,
                cost_usd=spend,
                detail=f"{deferred} deferred to next run" if deferred else "",
            )


def cap_batch(fresh, limit):
    """Split `fresh` (ascending by `updated`) into this run's share and a count left over.

    A cut between two annotations sharing a timestamp is safe: the next fetch
    re-reads the cursor's millisecond (see ms_before) and `seen` skips the
    first.
    """
    if limit <= 0 or len(fresh) <= limit:
        return fresh, 0
    return fresh[:limit], len(fresh) - limit


if __name__ == "__main__":
    main()
