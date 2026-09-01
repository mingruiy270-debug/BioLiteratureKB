---
name: bio-literature-kb
description: Use the user's local biomedical literature knowledge base to support any scientific-research task — topic selection, study design, bioinformatics analysis, dry-wet integration, paper writing, revision, review, presentation, and more — without loading the full paper library into context. Learn transferable methods and writing patterns from papers across diseases and topics, not just the user's own field.
---

# BioLiteratureKB

The knowledge base is an external literature memory and retrieval system for the full research lifecycle — from topic selection and study design, through data analysis, to paper writing and revision.

It is not an authority and it is not a pre-built bioinformatics agent.

## When to use

Use the KB for any science-related task, not just analysis design:

- **Topic selection**: identify gaps, frontier directions, and what is now possible.
- **Study design**: analysis strategy, experimental design, evidence-chain structure.
- **Analysis**: bioinformatics, multi-omics, ML, single-cell, spatial, perturbation.
- **Dry-wet integration**: bridge computational findings to wet-lab validation.
- **Paper writing**: Introduction framing, Methods wording and structure, Results narrative, Discussion logic, figure organization, limitations and caveats — learn how high-quality papers in the library phrase and structure these.
- **Revision / review**: compare claims against the literature, find counter-evidence, anticipate reviewer questions.
- **Presentation**: background, take-home messages, evidence summaries.
- Anything else science-related.

Do not assume the task is analysis-only. If the user is writing or revising text about their research, retrieve papers to learn how the field phrases, structures, and justifies comparable claims.

## Prerequisites

The `biokb` CLI must be installed. It is a local Python package (see the repo's `install.bat` / `install.sh`, or install with `pip install -e .`).

Run `biokb doctor` to verify the environment.

## Available commands

Search candidate papers:

`biokb search "<query>" --top 10`

Read a deep structured paper digest:

`biokb digest <paper_id>`

Retrieve targeted passages from one paper:

`biokb excerpt <paper_id> "<query>" --top 5`

Search targeted passages across the whole library:

`biokb search-fulltext "<query>" --top 10`

Check library status:

`biokb status`

Environment self-check:

`biokb doctor`

All commands support `--json` for machine-readable output.

The number of papers to search, digest, or excerpt is your choice — decide it per task (how many candidates the question needs, how much depth the decision requires), not by a fixed cap. `--top N` is adjustable in every search command.

## Cross-topic learning principle

Do not restrict retrieval to papers on the user's disease, tissue, or species. The library's value lies in transferable methodology: frontier analysis strategies, experimental designs, evidence-chain structures, and writing patterns often come from other diseases and other topics.

Read across the library to learn how to combine high-quality patterns with the user's specific project, and to elevate the user's research:

- the user's own field papers → direct benchmarks, gaps, and conventions;
- other-disease / other-tissue papers → methodological patterns to transplant;
- frontier multi-omics / ML / spatial / perturbation papers → what is now possible.

Judge each paper by methodological and rhetorical transferability, not by topic similarity.

## Workflow

When the user asks for scientific help:

1. First understand the current project and the exact task:
   - scientific question,
   - existing datasets,
   - completed analyses,
   - important results,
   - wet-lab evidence,
   - sample size,
   - experimental constraints,
   - time and computational constraints,
   - and, for writing tasks: target journal style, section being drafted, claims to be supported.

2. Decide what literature questions need to be answered — topic-specific questions, method-pattern questions, and, for writing tasks, convention and phrasing questions.

3. Generate several focused KB queries (mix disease-relevant and method-pattern queries).

4. Use `biokb search`.

5. Compare candidate Paper Digests before reading full text.

6. Select only the most relevant papers.

7. Use `biokb excerpt` for exact methodological, statistical, algorithmic, experimental, or wording details.

8. Read raw Markdown only when targeted retrieval is insufficient.

9. Never bulk-load the literature library.

10. Do not recommend a method merely because retrieved papers used it.

11. Determine yourself:
    - whether the method answers the current scientific question,
    - whether the required data exist,
    - whether it adds a meaningful evidence layer,
    - whether it can connect to downstream analyses or experiments,
    - whether a better alternative exists,
    - for writing tasks: whether a phrasing or structure fits the current manuscript.

## Web access

When the user permits web access, combine local and web evidence.

Use the local KB for:
- the user's curated literature,
- detailed methodological patterns,
- known relevant papers.

Use the web for:
- newer papers,
- newer algorithms,
- current software versions,
- recent documentation,
- newly available datasets,
- external verification.

Do not automatically privilege either source.

## Reasoning responsibility

All of the following belong to you at runtime, not to the KB:

- cross-paper synthesis,
- project-specific method selection,
- prioritization,
- innovation assessment,
- removal of low-value analyses,
- combination of methods from different papers,
- research workflow design,
- manuscript drafting and editing decisions.

Clearly distinguish:

1. findings reported by individual papers;
2. methodological patterns inferred across papers;
3. recommendations made specifically for the current project.

## Context discipline

Default retrieval order:

`search → digest → excerpt → raw Markdown → PDF`

Move deeper only when necessary.

Prefer several focused retrievals to one large context dump.
