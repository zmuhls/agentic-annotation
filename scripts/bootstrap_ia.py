#!/usr/bin/env python3
"""Draft an architecture/ia.md from the adopter's own annotation history.

`ia.md` is the one file a new adopter cannot copy from this repo: it is the
taxonomy the classifier reads on every poll, and the version committed here
describes one person's groups, sites, and projects. Written from scratch it is
an hour of staring at a blank page; written from your own history it is an
edit pass. So ask the API which groups you belong to (GET /api/profile/groups)
and where you actually annotate (GET /api/search), and emit a nodes section
with one top-level node per group, its busiest domains as children, and the
public layer folded into `reading`.

The cross-cutting half of the file — the action-tag vocabulary that `poll.py`
and `build_ia.py` both implement — is not personal, so it is carried over from
the existing ia.md verbatim rather than restated here.

    python3 scripts/bootstrap_ia.py            # print to stdout
    python3 scripts/bootstrap_ia.py --write    # write ./architecture/ia.md

Refuses to clobber an existing ia.md unless --force is passed.
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from appconfig import load_config  # noqa: E402

API = "https://api.hypothes.is/api"
OUT = ROOT / "architecture" / "ia.md"

NODES_HEADING = "## Nodes"
SHARED_TAIL_HEADING = "## Action vocabulary"
# Enough history to see which domains matter without paging: the sample only
# has to rank a person's sites, not enumerate them.
SAMPLE_LIMIT = 200
# A domain earns its own child node once it is more than a stray one-off.
DOMAIN_MIN_HITS = 2
DOMAIN_CHILDREN = 3


def get(path, token, **params):
    url = f"{API}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def slugify(text, fallback="group"):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:40].strip("-") or fallback


def domain_of(ann):
    return urllib.parse.urlparse(ann.get("uri", "")).netloc.lower().removeprefix("www.")


def domains_by_group(annotations):
    """{group id: Counter(domain)} over the sampled annotations."""
    counts = {}
    for ann in annotations:
        domain = domain_of(ann)
        if not domain:
            continue  # local files and PDFs without a URI tell us nothing
        counts.setdefault(ann.get("group", "__world__"), Counter())[domain] += 1
    return counts


def _unique(slug, taken):
    candidate, n = slug, 2
    while candidate in taken:
        candidate, n = f"{slug}-{n}", n + 1
    taken.add(candidate)
    return candidate


def nodes_section(groups, counts):
    """The one section of ia.md that is nobody else's to write."""
    lines = [NODES_HEADING, ""]
    taken = {"inbox", "reading"}
    for group in sorted(groups, key=lambda g: g.get("name", "")):
        gid = group.get("id")
        if not gid or gid == "__world__":
            continue  # the public layer becomes `reading`, below
        name = group.get("name") or gid
        slug = _unique(slugify(name), taken)
        seen = counts.get(gid, Counter())
        total = sum(seen.values())
        lines.append(f"### {slug} — {name}")
        lines.append(
            f"Annotations in the \"{name}\" group ({total} in a sample of the "
            f"{SAMPLE_LIMIT} most recent). Replace this line with what the group "
            "is actually for — the classifier reads it.")
        for domain, hits in seen.most_common(DOMAIN_CHILDREN):
            if hits < DOMAIN_MIN_HITS:
                break
            lines.append(f"- `{slug}/{slugify(domain, 'site')}` — {domain} ({hits})")
        lines.append(f"- `{slug}/general` — anything in this group the children above miss")
        lines.append("")

    public = counts.get("__world__", Counter())
    lines.append("### reading — public-layer annotation, outside any group")
    lines.append("Reading not tied to a project above.")
    for domain, hits in public.most_common(DOMAIN_CHILDREN):
        if hits < DOMAIN_MIN_HITS:
            break
        lines.append(f"- `reading/{slugify(domain, 'site')}` — {domain} ({hits})")
    lines.append("- `reading/general` — everything else worth keeping")
    lines.append("")
    lines.append("### inbox — unplaced")
    lines.append("Holding node when no rule or classification fits; reviewed periodically.")
    lines.append("")
    return "\n".join(lines)


def split_template(text):
    """(preamble, shared tail) of an existing ia.md — everything but the nodes.

    The tail is the action vocabulary and the file map: the same contract for
    every adopter, because poll.py and build_ia.py implement it in code.
    """
    head, sep, rest = text.partition(NODES_HEADING)
    if not sep:
        raise ValueError(f"no '{NODES_HEADING}' heading in {OUT.name}")
    marker = rest.find(SHARED_TAIL_HEADING)
    if marker == -1:
        raise ValueError(f"no '{SHARED_TAIL_HEADING}' heading in {OUT.name}")
    return head, rest[marker:]


def first_child(section):
    """The first `group/child` node id the draft defines, for use as an example."""
    match = re.search(r"^- `([^`]+)`", section, re.MULTILINE)
    return match.group(1) if match else None


def draft(template_text, user, groups, counts):
    preamble, tail = split_template(template_text)
    section = nodes_section(groups, counts)
    # The committed preamble is about the schema and stays as written, except
    # for the two places it can only speak for its author: the account it
    # watches, and the node it reaches for as an example. Both would read as
    # someone else's taxonomy in a file meant to become yours.
    preamble = re.sub(r"`acct:[^`]*`", f"`{user}`", preamble)
    example = first_child(section)
    if example:
        preamble = re.sub(r"\(e\.g\. `[^`]+`\)", f"(e.g. `{example}/<child>`)",
                          preamble, count=1)
    return preamble + section + tail


def main():
    config = load_config()
    token = config.get("api_token", "")
    if not token or token.startswith("YOUR-"):
        sys.exit("no api_token in config.json — copy config.example.json first")
    user = config.get("user", "")
    if not user:
        sys.exit("no user in config.json — set it to acct:<you>@hypothes.is")

    if not OUT.exists():
        sys.exit(f"{OUT} is missing — it is the template this script rewrites")
    template_text = OUT.read_text()

    groups = get("profile/groups", token)
    annotations = get("search", token, user=user, sort="updated",
                      order="desc", limit=SAMPLE_LIMIT).get("rows", [])
    text = draft(template_text, user, groups, domains_by_group(annotations))

    if "--write" not in sys.argv:
        print(text, end="")
        print(f"\n# {len(groups)} group(s), {len(annotations)} annotation(s) sampled; "
              "re-run with --write --force to save to architecture/ia.md",
              file=sys.stderr)
        return
    if "--force" not in sys.argv:
        sys.exit(f"{OUT.name} already exists — pass --force to overwrite")
    OUT.write_text(text)
    print(f"wrote {OUT} from {len(groups)} group(s); now edit each node's "
          "description and prune what you do not want")


if __name__ == "__main__":
    main()
