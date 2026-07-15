# Hypothesis Annotation Information Architecture

Taxonomy for all annotations by `acct:zachmuhlbauer@hypothes.is`. Every
annotation is assigned one **node** (where it lives) and optionally one
**workflow status** (what should happen to it). The initial sort was
rule-based (see `scripts/build_ia.py`); new annotations are placed by
Claude Sonnet 5 via `scripts/poll.py`.

Node IDs are slash paths. Sonnet may propose deeper children under an
existing node (e.g. `dissertation/corpus/transfer`) but may not invent new
top-level nodes; genuinely unplaceable annotations go to `inbox` and are
listed in `architecture/emergent-nodes.md` for review.

## Nodes

### artifacts — notes on your own written artifacts & development objects
Annotations on pages you author or build. These are self-addressed editorial
notes; they carry workflow tags and are the primary source of action files.
- `artifacts/personal-site` — zmuhls.github.io and its localhost:4000 previews
- `artifacts/cuny-ai-lab` — cuny-ai-lab.github.io tutorials, docs, lab pages
- `artifacts/inference-arcade` — bot.inference-arcade.com experiments
- `artifacts/other` — any other self-authored artifact or dev object

### dissertation — CUNY Reddit dissertation research
Annotations in the `diss` group, plus Reddit corpus material and scholarship
read for chapters.
- `dissertation/sources` — scholarly reading for the diss (methods, theory, lit review)
- `dissertation/corpus` — Reddit threads, CUNY community material, primary sources
- `dissertation/drafting` — notes toward argument, chapter, or prose moves

### ai-pedagogy — AI, teaching, and the CUNY AI Lab orbit
AI FIG | TLC group, Toolkit Annotations, TLC Social Reading Group, and
reading about AI in education (criticaledtech.com and kin).
- `ai-pedagogy/fig` — AI FIG / TLC social annotation
- `ai-pedagogy/toolkit` — AI toolkit and tutorial source material
- `ai-pedagogy/reading` — scholarship and commentary on AI + education

### teaching — course-facing annotation
Course groups: CSC10800, ENG 2100/2150 sections, Lesson Prep, ITP.
- `teaching/csc10800` — CSC10800 Annotation Group
- `teaching/writing-courses` — ENG 2100 / ENG 2150 sections
- `teaching/prep` — Lesson Prep, ITP, other instructional planning

### reading — general intellectual reading not tied to a project above
Public-layer and N.B. group annotation of scholarship and the open web.
- `reading/digital-humanities` — DH methods, cultural analytics, text analysis
- `reading/ai-ml` — AI/ML technical and critical reading
- `reading/general` — everything else worth keeping

### inbox — unplaced
Holding node when no rule or classification fits; reviewed periodically.

## Action vocabulary (from tags, cross-cutting)

Any of these tags on an annotation makes it an editorial directive: the
watcher has Sonnet write a concrete instruction file into `actions/`, one
file per action tag (tags combine — e.g. `hedge` + `cite` yields two files).
The annotation's note states intent; the instructions operationalize it
against the anchored passage.

### Prose & argument (for written artifacts)

| Tag           | Directive |
|---------------|-----------|
| `revision`    | Rework the anchored prose — style, syntax, actor-action clarity — per the note |
| `expansion`   | Add new material at the anchor: what to add, where it attaches, what it must accomplish |
| `condense`    | Tighten or cut: what to remove, what must survive, target length |
| `restructure` | Reorder or reshape the section/argument around the anchor; fix motion and flow, propose the new sequence |
| `hedge`       | Recalibrate claim strength to the evidence: scope, frequency, causality; supply the hedged rewrite |
| `reframe`     | Recast the passage through a different lens, register, or audience named in the note |
| `exemplify`   | Supply a concrete example, scene, or illustration for the abstract claim at the anchor |
| `counter`     | Generate the strongest objections to the anchored argument and how the text should answer them |
| `define`      | Clarify or define the term at the anchor; propose the definition and where it belongs |

### Research & evidence

| Tag          | Directive |
|--------------|-----------|
| `cite`       | Find or verify a citable source for the anchored claim; produce citation candidates and where each would slot in |
| `evidence`   | Specify what empirical/corpus evidence would ground the claim and exactly how to query for it (e.g. the Reddit corpus databases) |
| `verify`     | Fact-check the anchored claim: enumerate what must be confirmed, against what source, and what would falsify it |
| `question`   | Turn the note into a research brief: the question sharpened, what to read/search/test, expected outputs |
| `synthesize` | Connect this annotation with its siblings at the same node; draft the synthesis note that binds them |

### Development objects (sites, tools, code)

| Tag       | Directive |
|-----------|-----------|
| `bug`     | Describe the defect at the anchor, likely cause, reproduction, and fix instructions |
| `feature` | Turn the note into a small feature spec: behavior, placement, acceptance criteria |
| `a11y`    | Accessibility fix for the anchored element: what fails, which guideline, the remedy |

### Status (tracked, no action file)

| Tag           | Meaning |
|---------------|---------|
| `outstanding` | Open item awaiting action |
| `resolved`    | Item handled |

## Files

- `architecture/map.jsonl` — one line per annotation: `{id, node, workflow, uri, title, created, tags, quote, note, link}`
- `architecture/overview.md` — regenerated counts per node (do not hand-edit)
- `architecture/emergent-nodes.md` — nodes Sonnet proposed beyond this doc, for review
- `actions/` — generated instruction files for revision/expansion/condense annotations
