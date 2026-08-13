"""检索层：search / digest / excerpt / search-fulltext，支持 citekey 别名解析。"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from .indexer import Indexer


class NotFound(Exception):
    pass


def _resolve_alias(db: Path, paper_id_or_citekey: str) -> str:
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT paper_id FROM papers WHERE paper_id=? OR citekey=?", (paper_id_or_citekey, paper_id_or_citekey)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise NotFound(f"未找到论文: {paper_id_or_citekey}（可用 biokb search 查询 paper_id / citekey）")
    return row[0]


class Retrieval:
    def __init__(self, cfg):
        self.cfg = cfg
        self.idx = Indexer(cfg.index_db)

    def search(self, query: str, top: Optional[int] = None) -> List[dict]:
        return self.idx.search(query, top or self.cfg.default_search_top)

    def digest(self, paper_id_or_citekey: str) -> dict:
        pid = _resolve_alias(self.cfg.index_db, paper_id_or_citekey)
        meta, text = self.idx.get_digest(pid)
        if not text:
            raise NotFound(f"论文 {pid} 尚无 Digest（DIGEST_PENDING / 未生成）")
        return {"paper_id": pid, **meta, "digest": text}

    def excerpt(self, paper_id_or_citekey: str, query: str, top: Optional[int] = None, max_chars: Optional[int] = None) -> List[dict]:
        pid = _resolve_alias(self.cfg.index_db, paper_id_or_citekey)
        return self.idx.excerpt(pid, query, top or self.cfg.default_excerpt_top, max_chars or self.cfg.default_max_chars)

    def search_fulltext(self, query: str, top: Optional[int] = None, max_chars: Optional[int] = None) -> List[dict]:
        return self.idx.search_fulltext(query, top or self.cfg.default_search_top, max_chars or self.cfg.default_max_chars)
