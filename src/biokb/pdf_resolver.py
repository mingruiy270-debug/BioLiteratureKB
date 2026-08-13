"""PDF 定位：四级解析 + 模糊匹配 + 歧义二次验证。

Level 1: Zotero attachment 明确本地路径（不做 fuzzy）
Level 2: Zotero attachment key → storage/<key>/ 单 PDF
Level 3: attachment filename 在 inventory 中精确匹配
Level 4: inventory 模糊匹配（截断标题 / 标点 / Unicode / 作者年份前缀）
结果: matched | ambiguous | missing
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from .models import InventoryEntry, PaperRecord
from .pdf_inventory import normalize_pdf_filename

ACCEPT_MIN = 70.0
AMBIGUITY_GAP = 12.0


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[^a-z0-9一-鿿]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_author_year_prefix(normalized_stem: str) -> str:
    """把 `chen 等 2026 decoding ...` 剥离为 `decoding ...`。

    输入已是 normalize_pdf_filename 产物（空格分隔、全小写）。
    """
    parts = normalized_stem.split(" ")
    # 作者段：首个 token 若以姓氏样式开头且随后是 等/et al，或第2个 token 是年份
    title_start = 0
    if len(parts) >= 2 and re.fullmatch(r"(19|20)\d{2}", parts[1] or ""):
        # 形如 chen 等 2026 title...
        title_start = 2 if (len(parts) >= 3 and parts[2]) else 1
    elif parts and re.fullmatch(r"(19|20)\d{2}", parts[0] or ""):
        title_start = 1
    elif len(parts) >= 2 and (parts[1] in ("等",) or parts[1] in ("et", "al") or parts[1].endswith("al")):
        # 形如 chen 等 title...（无年份）
        title_start = 2
        if title_start < len(parts) and re.fullmatch(r"(19|20)\d{2}", parts[title_start] or ""):
            title_start += 1
    return " ".join(parts[title_start:]).strip()


def _candidate_stems(entry: InventoryEntry) -> List[str]:
    """生成多个候选 stem：全量 + 剥离作者年份前缀，去重。"""
    full = entry.normalized_stem
    stripped = _strip_author_year_prefix(full)
    out = [full]
    if stripped and stripped != full:
        out.append(stripped)
    return out


def _token_overlap(norm_title: str, stem: str) -> float:
    """有序 token 覆盖率：title 中有多少比例 token 按顺序出现在 stem 中。"""
    tt = norm_title.split(" ")
    st = stem.split(" ")
    if not tt:
        return 0.0
    j, hit = 0, 0
    for t in tt:
        while j < len(st) and st[j] != t:
            j += 1
        if j < len(st):
            hit += 1
            j += 1
    return hit / len(tt)


def _prefix_score(norm_title: str, stem: str) -> float:
    """截断标题识别：一方是另一方的长前缀。"""
    if not norm_title or not stem:
        return 0.0
    if norm_title.startswith(stem) or stem.startswith(norm_title):
        cov = min(len(stem), len(norm_title)) / max(len(stem), len(norm_title), 1)
        return 100.0 * (cov ** 0.7)
    return 0.0


def score_candidate(record: PaperRecord, entry: InventoryEntry) -> float:
    """0–100，含作者/年份证据加分。"""
    norm_title = _norm(record.title)
    if not norm_title:
        return 0.0
    best_core = 0.0
    for stem in _candidate_stems(entry):
        core = max(
            _prefix_score(norm_title, stem),
            fuzz.partial_ratio(norm_title, stem),
            fuzz.token_set_ratio(norm_title, stem),
            100.0 * _token_overlap(norm_title, stem),
        )
        best_core = max(best_core, core)
    # 作者与年份证据（针对原始文件名）
    raw_lower = entry.filename.lower()
    bonus = 0.0
    if record.authors:
        fam = _norm(record.authors[0].split(" ")[0])
        if fam and fam in raw_lower:
            bonus += 8.0
    if record.year and str(record.year) in raw_lower:
        bonus += 5.0
    return min(100.0, best_core + bonus)


# --------------------------------------------------------------------------
# 二次验证：读取 PDF 前两页文本，核对 title / DOI / 第一作者 / 年份
# --------------------------------------------------------------------------

def _pdf_head_text(path: Path, max_pages: int = 2, max_chars: int = 6000) -> str:
    try:
        import pymupdf  # PyMuPDF ≥1.26

        doc = pymupdf.open(path)
        text = "".join(doc[p].get_text() for p in range(min(max_pages, doc.page_count)))
        doc.close()
        return text[:max_chars]
    except Exception:  # noqa: BLE001
        return ""


def _verify_candidates(record: PaperRecord, candidates: List[Tuple[InventoryEntry, float]]) -> Optional[InventoryEntry]:
    """歧义时读 PDF 头页验证；验证不清则返回 None（→ PDF_AMBIGUOUS）。"""
    if not candidates:
        return None
    norm_title = _norm(record.title)
    doi_norm = record.doi.lower()
    fam = _norm(record.authors[0].split(" ")[0]) if record.authors else ""
    scores: List[Tuple[InventoryEntry, float]] = []
    heads: Dict[int, str] = {}
    for entry, _ in candidates:
        text = _pdf_head_text(Path(entry.path))
        heads[id(entry)] = text
        if not text:
            scores.append((entry, 0.0))
            continue
        t = _norm(text)
        s = 0.0
        if norm_title and (norm_title in t or fuzz.partial_ratio(norm_title, t) > 60):
            s += 40.0
        if doi_norm and doi_norm in t:
            s += 30.0
        if fam and fam in t:
            s += 20.0
        if record.year and str(record.year) in t:
            s += 10.0
        scores.append((entry, s))
    scores.sort(key=lambda x: x[1], reverse=True)
    if not scores or scores[0][1] < 50.0:
        return None  # 验证失败 → ambiguous
    if len(scores) > 1 and scores[0][1] - scores[1][1] < 30.0:
        # 两候选头部文本近乎相同 → 同一论文的不同副本 → 取高分者
        t0 = _norm(heads.get(id(scores[0][0]), ""))[:3000]
        t1 = _norm(heads.get(id(scores[1][0]), ""))[:3000]
        if t0 and t1 and fuzz.token_set_ratio(t0, t1) > 95:
            return scores[0][0]
        return None  # 仍接近 → ambiguous
    return scores[0][0]


# --------------------------------------------------------------------------
# 主解析入口
# --------------------------------------------------------------------------

def resolve_pdf(
    record: PaperRecord,
    inventory: List[InventoryEntry],
    storage_root: Path,
) -> Tuple[Optional[str], str, List[Tuple[InventoryEntry, float]]]:
    """返回 (pdf_path | None, status, debug_candidates)。status ∈ matched|ambiguous|missing"""
    # Level 1: attachment 明确路径
    if record.attachment.source_path:
        p = Path(record.attachment.source_path)
        if p.exists():
            return str(p), "matched", []
        # Zotero 有时存相对路径
        p2 = storage_root / record.attachment.source_path
        if p2.exists():
            return str(p2), "matched", []
    # Level 2: attachment key → storage/<key>/
    if record.attachment.zotero_attachment_key:
        folder = storage_root / record.attachment.zotero_attachment_key
        if folder.exists():
            pdfs = [f for f in folder.glob("*.pdf")]
            if len(pdfs) == 1:
                return str(pdfs[0]), "matched", []
            if len(pdfs) > 1:
                return None, "ambiguous", []
    # Level 3: attachment filename 精确匹配
    if record.attachment.original_filename:
        target = record.attachment.original_filename.lower()
        for e in inventory:
            if e.filename.lower() == target:
                return e.path, "matched", []
    # Level 4: 模糊匹配
    scored = [(e, score_candidate(record, e)) for e in inventory]
    # Zotero 中同一论文 PDF 常重复存在于多个 storage 文件夹 → 按 (文件名, 大小) 去重
    seen: Dict[tuple, tuple] = {}
    for e, s in scored:
        key = (e.filename.lower(), e.size)
        if key not in seen or s > seen[key][1]:
            seen[key] = (e, s)
    scored = list(seen.values())
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [s for s in scored if s[1] >= ACCEPT_MIN][:4]
    if not top:
        return None, "missing", scored[:4]
    if len(top) == 1:
        return top[0][0].path, "matched", top
    if top[0][1] - top[1][1] >= AMBIGUITY_GAP:
        return top[0][0].path, "matched", top
    # 高度接近 → 二次验证
    verified = _verify_candidates(record, top)
    if verified:
        return verified.path, "matched", top
    return None, "ambiguous", top
