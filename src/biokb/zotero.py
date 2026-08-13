"""Zotero / Better BibTeX JSON 解析。

兼容三种形态：
- 顶层 list（Better BibTeX CSL-JSON，如现有 高分论文参考.json）
- 顶层 {"items": [...]}
- Zotero 原生 JSON（含 key / attachments 字段）

字段名兼容 CSL-JSON 与 Zotero 原生命名：
citation-key | citationKey | citekey
container-title | publicationTitle | journal
DOI | doi
issued | date | year
author | creators
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AttachmentInfo, Author, PaperRecord

DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi:", "DOI:", "doi.org/", "https://dx.doi.org/", "http://dx.doi.org/")


def normalize_doi(raw: Optional[str]) -> str:
    """统一 DOI 为小写 `10.xxxx/abc` 形式；无法识别返回空串。"""
    if not raw:
        return ""
    s = raw.strip()
    for p in DOI_PREFIXES:
        if s.lower().startswith(p.lower()):
            s = s[len(p):]
            break
    s = s.strip().rstrip(".,;")
    if re.fullmatch(r"10\.\d{4,9}/.+", s, flags=re.IGNORECASE):
        return s.lower()
    return ""


def internal_id(item: Dict[str, Any]) -> str:
    """内部 ID：citekey 或 title 的短哈希。"""
    seed = item.get("citation-key") or item.get("citationKey") or item.get("citekey") or str(item.get("title", ""))
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _first(d: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def parse_year(item: Dict[str, Any]) -> Optional[int]:
    raw = _first(item, "issued", "date", "year", "publicationYear", default=None)
    if raw is None:
        return None
    if isinstance(raw, dict):
        parts = raw.get("date-parts", [[None]])
        if parts and parts[0]:
            y = parts[0][0]
            return int(y) if y else None
    if isinstance(raw, int):
        return raw
    m = re.search(r"(19|20)\d{2}", str(raw))
    return int(m.group(0)) if m else None


def parse_authors(item: Dict[str, Any]) -> List[str]:
    raw = _first(item, "author", "creators", "authors", default=[])
    names: List[str] = []
    for a in raw or []:
        if isinstance(a, str):
            names.append(a)
            continue
        fam = a.get("family") or a.get("lastName") or a.get("name") or ""
        giv = a.get("given") or a.get("firstName") or ""
        if fam:
            names.append(f"{fam} {giv}".strip())
    return names


def parse_attachments(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = _first(item, "attachments", default=[])
    if not isinstance(raw, list):
        return []
    out = []
    for a in raw:
        if not isinstance(a, dict):
            continue
        mime = str(a.get("mimeType") or a.get("mimetype") or "")
        if mime and "pdf" not in mime.lower():
            continue
        out.append(
            {
                "zotero_attachment_key": a.get("key") or a.get("attachmentKey") or "",
                "original_filename": a.get("filename") or a.get("title") or "",
                "source_path": a.get("path") or a.get("source_path") or "",
            }
        )
    return out


def parse_item(item: Dict[str, Any]) -> PaperRecord:
    title = str(_first(item, "title", default="")).strip()
    citekey = str(_first(item, "citation-key", "citationKey", "citekey", default="")).strip()
    zkey = str(_first(item, "key", "itemKey", default="")).strip()
    doi = normalize_doi(_first(item, "DOI", "doi", default=""))
    pmid = str(_first(item, "PMID", "pmid", default="")).strip()

    paper_id = zkey or doi or internal_id(item)
    atts = parse_attachments(item)
    att = AttachmentInfo()
    if atts:
        a = atts[0]
        att = AttachmentInfo(
            zotero_attachment_key=a["zotero_attachment_key"],
            original_filename=a["original_filename"],
            source_path=a["source_path"],
        )

    return PaperRecord(
        paper_id=paper_id,
        citekey=citekey,
        zotero_item_key=zkey,
        title=title,
        doi=doi,
        pmid=pmid,
        year=parse_year(item),
        authors=parse_authors(item),
        journal=str(_first(item, "container-title", "publicationTitle", "journal", default="")).strip(),
        url=str(_first(item, "URL", "url", default="")).strip(),
        abstract=str(_first(item, "abstract", "abstractNote", default="")).strip(),
        attachment=att,
    )


def load_json_files(json_dir: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not json_dir.exists():
        return items
    for fp in sorted(json_dir.glob("*.json")):
        try:
            with open(fp, encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001
            continue  # 坏文件记录到日志层，不在此抛
        if isinstance(data, list):
            items.extend(data)
        elif isinstance(data, dict):
            items.extend(data.get("items", []) or [])
    return items


def parse_all(json_dir: Path) -> List[PaperRecord]:
    """解析全部 JSON 并去重（按 paper_id）。返回 (records, duplicates 信息)。"""
    records: Dict[str, PaperRecord] = {}
    dup = 0
    for item in load_json_files(json_dir):
        rec = parse_item(item)
        if not rec.title and not rec.doi:
            continue
        if rec.paper_id in records:
            dup += 1
        records[rec.paper_id] = rec
    return list(records.values()), dup
