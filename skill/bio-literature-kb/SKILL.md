---
name: bio-literature-kb
description: Use the user's local research literature knowledge base to support any-domain scientific-research task — topic selection, study design, analysis, paper writing, revision, review, presentation, and more — without loading the full paper library into context. Biomedicine works out of the box; any other domain (deep learning, machine learning, etc.) is supported via a project-specific digest prompt. Learn transferable methods and writing patterns across topics and fields. Web search is allowed and encouraged to supplement the library's coverage.
---

# BioLiteratureKB

The knowledge base is an external literature memory and retrieval system for the full research lifecycle — from topic selection and study design, through data analysis, to paper writing and revision.

It is not an authority and it is not a pre-built bioinformatics agent.

## When to use

Use the KB for any science-related task, not just analysis design:

- **Topic selection**: identify gaps, frontier directions, and what is now possible.
- **Study design**: analysis strategy, experimental design, evidence-chain structure.
- **Analysis**: bioinformatics, multi-omics, ML, single-cell, spatial, perturbation — or, in other domains, modeling, training, evaluation, benchmarking.
- **Dry-wet integration**: bridge computational findings to experimental validation.
- **Paper writing**: Introduction framing, Methods wording and structure, Results narrative, Discussion logic, figure organization, limitations and caveats — learn how high-quality papers in the library phrase and structure these.
- **Revision / review**: compare claims against the literature, find counter-evidence, anticipate reviewer questions.
- **Presentation**: background, take-home messages, evidence summaries.
- Anything else science-related.

The pipeline is domain-agnostic: the default digest prompt targets biomedicine, and a customized prompt (see below) adapts extraction depth and vocabulary to any field — deep learning, machine learning, computer vision, NLP, materials, etc.

Do not assume the task is analysis-only. If the user is writing or revising text about their research, retrieve papers to learn how the field phrases, structures, and justifies comparable claims.

## Prerequisites

The `biokb` CLI must be installed. It is a local Python package (see the repo's `install.bat` / `install.sh`, or install with `pip install -e .`).

Run `biokb doctor` to verify the environment.

## PDF reading and cost-controlled pilots

For PDF ingestion quality, figures/formulas, or a paid single-paper test, read
[PDF reading](references/pdf-reading.md). Prefer `biokb review-pdf` (offline plan
by default; `--apply` explicitly permits API calls). It combines in-scope native
text with selected visual supplements and records coverage and bounded usage.
Text/captions are the default. Use vision only for important information that
text cannot convey; technical image detection is candidate triage, not a reason
to send every figure. Explicit page/crop selection is required for paid vision.
For important equations use the local `equations.json` candidate index and the
formula contract in that reference; unresolved extraction is not author omission.
Use `--formula-crops` only where native text cannot resolve essential math.
Prioritize the paper's scientific subject: core question, methods, results and
limits. Do not enumerate unrelated bibliography or chase every supplement.
Use explicit `--text-pages` when appendices/reference-only pages are irrelevant;
keep Methods even when placed after References, and disclose excluded pages.
For important in-scope scanned text, optional `--ocr-sparse --ocr-tessdata ...`
uses local OCR; excluded supplementary scans need not block the main-paper review.
Do not describe parser installation, Markdown length or a completed API request
as evidence of correct full-text reading. Never automatically retry uncertain
billable requests or silently truncate material to meet a budget.

## Available commands

Search candidate papers:

`biokb search "<query>"`

Read a deep structured paper digest:

`biokb digest <paper_id>`

Retrieve targeted passages from one paper:

`biokb excerpt <paper_id> "<query>"`

Search targeted passages across the whole library:

`biokb search-fulltext "<query>"`

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

## Project-specific digest prompts (first use or on request)

Paper Digests follow a versioned prompt (`prompts/paper_digest_v1.md` by default).
The optional `research_deepread_v2` prompt is a generic, implementation- and
evidence-aware reader across research domains. Single-paper reading should first
preserve the paper's own useful knowledge, failures and reusable assets; project
selection and cross-paper synthesis are separate. Add project-specific focus
only when the user requests it, not as a mandatory part of every customization.

This is a **one-time or rare setup step** — do it only when:

- this skill is being set up for the user for the first time, and the user provides project documents (study design, analysis summaries, wet-lab results, project notes), or
- the user explicitly asks to change the digest prompt.

Do not propose customization during ordinary retrieval tasks.

This customization is also how the KB adapts to domains beyond biomedicine: the project focus section simply carries the target field's vocabulary and reading priorities (e.g., for deep learning / ML papers: architecture, dataset and benchmark, training strategy, ablations, metrics, reproducibility).

Workflow (may be executed autonomously by the agent, with the user only providing documents and doing final acceptance):

1. Read the project documents the user points to (design file, summaries, CLAUDE.md, etc.) and identify what the project cares about: background, core questions, domain terms, method families, reading priorities, conventions.
2. Run `biokb digest-prompt create <name>` to derive a new prompt from the active version.
3. Edit `prompts/paper_digest_<name>.md`. Keep generic reading generic; add `## 项目聚焦` only for explicitly requested project focus. Never filter away key evidence just because it is outside a current project.
4. Show the user the draft before anything else happens.
5. With authorization for the API expense, prefer a `review-pdf` pilot with an explicit page/cost budget; `digest-prompt test` is the older text-only preview and has different cost behavior. Let the user check quality.
6. If the user approves, activate with `biokb digest-prompt use <name>`. Activation does not authorize `sync`: disclose the scope, time and cost of re-reading the library and obtain separate authorization before a bulk refresh.

Customization may change extraction depth, emphasis, and vocabulary — it must never relax the fact discipline: `not_reported` / `unclear` / `null`, no fabrication, no claiming predictions as causation, and no project advice inside a single-paper digest.

## Web access (enabled by default)

Web access is allowed while using this skill. The library is not omniscient: it only contains the papers the user has curated, and it lags behind the frontier. When local retrieval cannot answer the question, actively search the web for supplementary information rather than stopping at the library's boundaries.

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
- external verification,
- anything the library does not cover.

Combine both sources and weigh them by relevance and recency. Do not automatically privilege either source, and do not treat the library's silence as evidence of absence.

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
