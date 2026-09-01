# Local BioLiteratureKB

A local biomedical literature knowledge base is available through the `biokb` CLI.

For any science-related task — topic selection, study design, bioinformatics, multi-omics, ML/DL, single-cell, dry-wet integration, paper writing, revision, review — use the BioLiteratureKB skill when local literature could materially improve the answer.

Do not bulk-load raw papers.

Web search is allowed and encouraged: the library is not omniscient, and the agent should supplement local retrieval with web evidence when the library lacks coverage.

Use:

`search → digest → excerpt`

and let the runtime agent perform the actual scientific reasoning.

## Quick commands

```bash
biokb search "single cell spatial"    # 检索候选论文
biokb digest <paper_id>               # 深度精读（支持 citekey 别名）
biokb excerpt <paper_id> "CellChat"   # 单篇原文精准段落
biokb search-fulltext "<query>"       # 跨库原文段落
biokb status                          # 状态总览
biokb sync                            # 增量同步
```

See `skill/bio-literature-kb/SKILL.md` for the full workflow, and `README.md` for system details.
