"""Zotero storage PDF inventory。首次全量扫描，之后增量使用缓存。"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List

from .models import InventoryEntry

_SEP_RE = re.compile(r"[\s_\-–—\.]+")


def normalize_pdf_filename(filename: str) -> str:
    """PDF 文件名 → 标题化 stem（保留前缀，解析阶段另行剥离作者年份前缀）。"""
    stem = Path(filename).stem
    stem = unicodedata.normalize("NFKC", stem)
    stem = stem.lower()
    # 去掉 .pdf 及残留扩展名后缀（如 .pdb、.ris）
    for ext in (".pdf", ".pdb", ".ris"):
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
    # 去掉卷号标记 "[v1]" 等
    stem = re.sub(r"\[v\d+\]$", "", stem)
    stem = _SEP_RE.sub(" ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def scan_storage(storage_root: Path) -> List[InventoryEntry]:
    entries: List[InventoryEntry] = []
    if not storage_root.exists():
        return entries
    for pdf in storage_root.rglob("*.pdf"):
        try:
            st = pdf.stat()
            entries.append(
                InventoryEntry(
                    path=str(pdf),
                    folder=pdf.parent.name,
                    filename=pdf.name,
                    normalized_stem=normalize_pdf_filename(pdf.name),
                    size=st.st_size,
                    mtime=st.st_mtime,
                )
            )
        except OSError:
            continue
    return entries


def load_inventory(path: Path) -> List[InventoryEntry]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [InventoryEntry(**d) for d in data]


def save_inventory(path: Path, entries: List[InventoryEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([e.model_dump() for e in entries], f, ensure_ascii=False, indent=1)


def index_by_filename(entries: List[InventoryEntry]) -> Dict[str, InventoryEntry]:
    out: Dict[str, InventoryEntry] = {}
    for e in entries:
        out.setdefault(e.filename.lower(), e)
    return out


def index_by_folder(entries: List[InventoryEntry]) -> Dict[str, List[InventoryEntry]]:
    out: Dict[str, List[InventoryEntry]] = {}
    for e in entries:
        out.setdefault(e.folder, []).append(e)
    return out
