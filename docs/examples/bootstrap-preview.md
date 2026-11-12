# Bootstrap preview: a fictional account

This is what `scripts/bootstrap.py` drafts for a made-up account. The groups,
ids, and domains are invented, and every domain is a reserved `example.*` name.
The output below came from running `bootstrap.drafts()` and
`bootstrap.summary()` on this input against the committed
`architecture/ia.md`. It was not written by hand.

## The input

The API calls return three groups plus the public layer, and a sample of 28
recent annotations:

| Group | Id | Annotations sampled |
| --- | --- | --- |
| Public | `__world__` | 5 on news.example.com, 3 on blog.example.org |
| Reading Seminar | `Ab12Cd34` | 9 on journals.example.edu, 4 on www.example.org, 1 on stray.example.net |
| Lab Notebook | `Ef56Gh78` | 6 on docs.example.com |
| Book Club | `Ij90Kl12` | none |

## The preview

```sh
python3 scripts/bootstrap.py
```

```text
ia.md: 14 node(s)
routing.json:
  Book Club → book-club/general
  Lab Notebook → lab-notebook/general
    docs.example.com → lab-notebook/docs-example-com
  Reading Seminar → reading-seminar/general
    journals.example.edu → reading-seminar/journals-example-edu
    example.org → reading-seminar/example-org
  Public → reading/general
    news.example.com → reading/news-example-com
    blog.example.org → reading/blog-example-org
0 group(s) still at inbox
```

Things to notice:

- Each group gets a top-level node and a `general` child. Its busiest domains
  get children of their own (up to three per group).
- A domain needs at least two hits in the sample to get a node, so the single
  annotation on stray.example.net goes to `reading-seminar/general`.
- `www.` is dropped from domains, so www.example.org becomes `example.org`.
- Book Club has no annotations in the sample, but it still gets a node,
  because the draft comes from the groups you belong to, not only the groups
  you have used.
- Public annotations go under `reading` instead of a group node.

## The drafted nodes section

`--write --force` replaces the `## Nodes` section of `architecture/ia.md`
with this. The action vocabulary below that section is copied over unchanged.

```markdown
## Nodes

### book-club — Book Club
Annotations in the "Book Club" group (0 in a sample of the 200 most recent). Replace this line with what the group is actually for — the classifier reads it.
- `book-club/general` — anything in this group the children above miss

### lab-notebook — Lab Notebook
Annotations in the "Lab Notebook" group (6 in a sample of the 200 most recent). Replace this line with what the group is actually for — the classifier reads it.
- `lab-notebook/docs-example-com` — docs.example.com (6)
- `lab-notebook/general` — anything in this group the children above miss

### reading-seminar — Reading Seminar
Annotations in the "Reading Seminar" group (14 in a sample of the 200 most recent). Replace this line with what the group is actually for — the classifier reads it.
- `reading-seminar/journals-example-edu` — journals.example.edu (9)
- `reading-seminar/example-org` — example.org (4)
- `reading-seminar/general` — anything in this group the children above miss

### reading — public-layer annotation, outside any group
Reading not tied to a project above.
- `reading/news-example-com` — news.example.com (5)
- `reading/blog-example-org` — blog.example.org (3)
- `reading/general` — everything else worth keeping

### inbox — unplaced
Holding node when no rule or classification fits; reviewed periodically.
```

## The drafted routing.json

These are the tables that matter. The full file also has a `_comment` and
empty `artifact_domains`, `domain_contains`, and `domain_nodes` tables, which
are for you to fill in by hand. `routing.example.json` documents all of them.

```json
{
  "group_names": {
    "__world__": "Public",
    "Ij90Kl12": "Book Club",
    "Ef56Gh78": "Lab Notebook",
    "Ab12Cd34": "Reading Seminar"
  },
  "group_domain_overrides": [
    {"group": "Ef56Gh78", "domain_contains": "docs.example.com", "node": "lab-notebook/docs-example-com"},
    {"group": "Ab12Cd34", "domain_contains": "journals.example.edu", "node": "reading-seminar/journals-example-edu"},
    {"group": "Ab12Cd34", "domain_contains": "example.org", "node": "reading-seminar/example-org"},
    {"group": "__world__", "domain_contains": "news.example.com", "node": "reading/news-example-com"},
    {"group": "__world__", "domain_contains": "blog.example.org", "node": "reading/blog-example-org"}
  ],
  "group_nodes": {
    "Ij90Kl12": "book-club/general",
    "Ef56Gh78": "lab-notebook/general",
    "Ab12Cd34": "reading-seminar/general"
  },
  "general_groups": ["__world__"],
  "general_node": "reading/general",
  "default_node": "inbox"
}
```

An override matches on part of the domain within its group. So in Reading
Seminar, `example.org` also catches an annotation on blog.example.org. An
annotation on blog.example.org in the public layer still goes to
`reading/blog-example-org`.

## What to edit before the first poll

1. Replace each "Replace this line…" description with one sentence saying what
   the group is for. The classifier reads `ia.md` on every poll.
2. Rename or delete nodes in `ia.md` as you like, such as `book-club` if the
   group is inactive. Then run
   `python3 scripts/bootstrap_routing.py --write --force` again. It redrafts
   `routing.json` against the new names, and any group whose node is gone
   starts at `inbox`. It writes the file from scratch, so make your own
   `routing.json` edits after this step, not before.
3. Point each group left at `inbox` at a node you kept, in `group_nodes`.
4. If you annotate your own work, add an `artifacts` node for it to `ia.md`
   and map each of your sites to it in `artifact_domains`. That table matches
   the exact domain (`www.` included) and wins over every group rule.
