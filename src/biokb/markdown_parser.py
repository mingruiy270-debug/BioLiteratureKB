"""Markdown 轻量 QC + section 分割。

QC：非空、字符量、section 关键词、乱码检测、非纯参考文献。
分割：heading 优先，无 heading 时按合理字符长度切块。
"""
from __future__ import annotations

import re
from typing import List, Tuple

SECTION_KEYWORDS = [
    "abstract", "introduction", "methods", "materials and methods", "results",
    "discussion", "conclusion", "supplementary", "single-cell analysis",
    "single cell analysis", "machine learning", "animal experiments",
    "statistical analysis", "experimental section", "data availability",
    "acknowledgements", "references",
]

HEADING_RE = re.compile(r"^#{1,4}\s+(.+)$", re.MULTILINE)
FALLBACK_CHUNK = 4000


def qc_check(md: str) -> Tuple[bool, str]:
    """(pass, reason)"""
    md = md.strip()
    if not md:
        return False, "empty"
    if len(md) < 1500:
        return False, f"too_short({len(md)})"
    low = md.lower()
    if not any(k in low for k in SECTION_KEYWORDS):
        return False, "no_known_sections"
    printable = sum(1 for c in md[:4000] if c.isprintable() or c in "\n\t")
    if printable / max(1, min(len(md), 4000)) < 0.9:
        return False, "garbled"
    # 只含参考文献 / 元数据
    body = md[2000:] if len(md) > 2000 else md
    if body and body.count("\n") > 50 and not any(k in body.lower() for k in SECTION_KEYWORDS[:6]):
        return False, "references_only"
    return True, "ok"


def split_sections(md: str) -> List[Tuple[str, str]]:
    """按 heading 分割；返回 [(section_name, text)]。"""
    # 去掉 frontmatter
    if md.startswith("---"):
        end = md.find("---", 3)
        if end != -1:
            md = md[end + 3:].lstrip("\n")
    matches = list(HEADING_RE.finditer(md))
    if len(matches) >= 2:
        sections = []
        for i, m in enumerate(matches):
            name = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
            text = md[start:end].strip()
            if text:
                sections.append((name, text))
        return sections
    # 无可靠 heading：按段落粗切
    paras = [p.strip() for p in re.split(r"\n\s*\n", md) if p.strip()]
    sections, buf, size = [], [], 0
    for p in paras:
        buf.append(p)
        size += len(p)
        if size >= FALLBACK_CHUNK:
            sections.append((f"chunk_{len(sections) + 1}", "\n\n".join(buf)))
            buf, size = [], 0
    if buf:
        sections.append((f"chunk_{len(sections) + 1}", "\n\n".join(buf)))
    return sections
