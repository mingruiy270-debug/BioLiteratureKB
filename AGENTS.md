# BioLiteratureKB

This repository provides a local biomedical literature knowledge base (`biokb` CLI).

When any science-related task — topic selection, study design, bioinformatics, multi-omics, ML/DL, single-cell, dry-wet integration, paper writing, revision, review — would benefit from the user's curated literature:

1. Use `biokb search "<query>"` to find candidate papers (short results only).
2. Read Paper Digests with `biokb digest <paper_id>` (paper_id or citekey).
3. Retrieve exact passages with `biokb excerpt <paper_id> "<query>"`.
4. Search across all papers with `biokb search-fulltext "<query>"`.

Never bulk-load the paper library. Web search is allowed and encouraged to supplement the library's coverage (the library is not omniscient). Do the scientific reasoning yourself at runtime.

Details: `skill/bio-literature-kb/SKILL.md` (behavior rules), `README.md` (system internals).
