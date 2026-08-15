---
name: bio-literature-kb
description: Use the user's local biomedical literature knowledge base to support bioinformatics, multi-omics, machine-learning, single-cell, dry-wet integrated and research-design tasks without loading the full paper library into context. Learn transferable methods from papers across diseases and topics, not just the user's own field.
---

# BioLiteratureKB

The knowledge base is an external literature memory and retrieval system.

It is not an authority and it is not a pre-built bioinformatics agent.

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

## Cross-topic learning principle

Do not restrict retrieval to papers on the user's disease, tissue, or species. The library's value lies in transferable methodology: frontier analysis strategies, experimental designs, and evidence-chain structures often come from other diseases and other topics.

Read across the library to learn how to combine high-quality patterns with the user's specific project, and to elevate the user's research design:

- the user's own field papers → direct benchmarks and gaps;
- other-disease / other-tissue papers → methodological patterns to transplant;
- frontier multi-omics / ML / spatial / perturbation papers → what is now possible.

Judge each paper by methodological transferability, not by topic similarity.

## Workflow

When the user asks you to improve or design a research workflow:

1. First understand the current project:
   - scientific question,
   - existing datasets,
   - completed analyses,
   - important results,
   - wet-lab evidence,
   - sample size,
   - experimental constraints,
   - time and computational constraints.

2. Decide what literature questions need to be answered — both topic-specific questions and cross-topic method-pattern questions.

3. Generate several focused KB queries (mix disease-relevant and method-pattern queries).

4. Use `biokb search`.

5. Compare candidate Paper Digests before reading full text.

6. Select only the most methodologically relevant papers.

7. Use `biokb excerpt` for exact methodological, statistical, algorithmic, experimental or result details.

8. Read raw Markdown only when targeted retrieval is insufficient.

9. Never bulk-load the literature library.

10. Do not recommend a method merely because retrieved papers used it.

11. Determine yourself:
    - whether the method answers the current scientific question,
    - whether the required data exist,
    - whether it adds a meaningful evidence layer,
    - whether it can connect to downstream analyses or experiments,
    - whether a better alternative exists.

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
- final research workflow design.

Clearly distinguish:

1. findings reported by individual papers;
2. methodological patterns inferred across papers;
3. recommendations made specifically for the current project.

## Context discipline

Default retrieval order:

`search → digest → excerpt → raw Markdown → PDF`

Move deeper only when necessary.

Prefer several focused retrievals to one large context dump.
