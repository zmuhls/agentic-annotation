#!/usr/bin/env python3
"""Full pull of Hypothesis annotations for the configured user.

Pages /api/search on `created` (ascending) from `since` in config.json and
writes one annotation per line to data/annotations.jsonl. Safe to re-run: it
replaces the file with a fresh complete pull, and only once every page is in,
so a failed pull leaves the previous file as it was.

Paging and retries are poll.py's (`fetch_new`, `search`): the api truncates
`search_after` to milliseconds, so a plain last-row cursor skipped annotations
created in the same millisecond as a page's last row, and one dropped
connection ended the whole pull. With no `since` it pulls the entire history.
"""

import json
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poll  # noqa: E402
from bootstrap_ia import require_token  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "annotations.jsonl"
# Before Hypothesis existed, so "no `since`" means everything.
EPOCH = "1970-01-01T00:00:00.000000+00:00"


def main():
    require_token(poll.CONFIG)
    if not poll.CONFIG.get("user"):
        sys.exit("no user in config.json — set it to acct:<you>@hypothes.is")
    since = poll.CONFIG.get("since") or EPOCH
    try:
        rows = poll.fetch_new(since, key="created")
    except urllib.error.HTTPError as e:  # a URLError/OSError subclass — catch first
        sys.exit(f"hypothesis api returned {poll.api_reason(e)}; {OUT.name} left as it was")
    except OSError as e:
        sys.exit(f"hypothesis api unreachable ({e}); {OUT.name} left as it was")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name(OUT.name + ".tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, OUT)  # atomic: a reader never sees half a pull
    print(f"wrote {len(rows)} annotations to {OUT}")


if __name__ == "__main__":
    main()
