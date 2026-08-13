"""SQLite / FTS5 索引。papers / digests / fulltext_fts 三表。"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

from .markdown_parser import split_sections
from .models import PaperRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    citekey TEXT,
    title TEXT,
    year INTEGER,
    doi TEXT,
    journal TEXT,
    status TEXT,
    digest_version TEXT
);
CREATE TABLE IF NOT EXISTS digests (
    paper_id TEXT PRIMARY KEY,
    digest_text TEXT,
    keywords TEXT,
    data_types TEXT,
    methods TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS fulltext_fts USING fts5(
    paper_id UNINDEXED,
    citekey UNINDEXED,
    title,
    section,
    text
);
CREATE VIRTUAL TABLE IF NOT EXISTS digests_fts USING fts5(
    paper_id UNINDEXED,
    digest_text,
    keywords,
    data_types,
    methods
);
"""


class Indexer:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_paper(self, rec: PaperRecord, status: str, digest_version: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO papers(paper_id, citekey, title, year, doi, journal, status, digest_version) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (rec.paper_id, rec.citekey, rec.title, rec.year, rec.doi, rec.journal, status, digest_version),
        )
        self._conn.commit()

    def upsert_digest(self, paper_id: str, digest_text: str, keywords: str, data_types: str, methods: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO digests(paper_id, digest_text, keywords, data_types, methods) VALUES (?,?,?,?,?)",
            (paper_id, digest_text, keywords, data_types, methods),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO digests_fts(paper_id, digest_text, keywords, data_types, methods) VALUES (?,?,?,?,?)",
            (paper_id, digest_text, keywords, data_types, methods),
        )
        self._conn.commit()

    def replace_fulltext(self, paper_id: str, citekey: str, title: str, md_text: str) -> int:
        """重建该论文的 FTS section 索引，返回 section 数。"""
        self._conn.execute("DELETE FROM fulltext_fts WHERE paper_id = ?", (paper_id,))
        sections = split_sections(md_text)
        rows = [
            (paper_id, citekey, _normalize_for_fts(title), sec, _normalize_for_fts(txt))
            for sec, txt in sections if txt.strip()
        ]
        self._conn.executemany(
            "INSERT INTO fulltext_fts(paper_id, citekey, title, section, text) VALUES (?,?,?,?,?)", rows
        )
        self._conn.commit()
        return len(rows)

    def has_paper(self, paper_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (paper_id,)).fetchone() is not None

    # ---- 查询 ----
    def search(self, query: str, top: int = 10) -> List[dict]:
        """跨 papers/digests/fulltext_fts 检索，返回论文级结果。"""
        q = _fts_query(query)
        best: Dict[str, float] = {}
        for sql, extra in (
            ("SELECT paper_id, bm25(fulltext_fts) AS score FROM fulltext_fts WHERE fulltext_fts MATCH ? ORDER BY score LIMIT ?", (q, top * 10)),
            ("SELECT paper_id, bm25(digests_fts) AS score FROM digests_fts WHERE digests_fts MATCH ? ORDER BY score LIMIT ?", (q, top * 10)),
        ):
            for pid, sc in self._conn.execute(sql, extra).fetchall():
                best[pid] = min(best.get(pid, 0.0), sc)  # bm25 越小越好
        ranked = sorted(best.items(), key=lambda x: x[1])[:top * 3]
        out = []
        for pid, sc in ranked:
            meta = self._conn.execute(
                "SELECT paper_id, citekey, title, year, doi, journal FROM papers WHERE paper_id=?", (pid,)
            ).fetchone()
            if not meta:
                continue
            dg = self._conn.execute(
                "SELECT keywords, data_types, methods FROM digests WHERE paper_id=?", (pid,)
            ).fetchone()
            out.append(
                {
                    "paper_id": meta[0], "citekey": meta[1], "title": meta[2], "year": meta[3],
                    "doi": meta[4], "journal": meta[5], "score": round(-sc, 3),
                    "keywords": dg[0] if dg else "", "data_types": dg[1] if dg else "",
                    "methods": dg[2] if dg else "",
                }
            )
        return out[:top]

    def get_digest(self, paper_id: str) -> Tuple[dict, str]:
        meta = self._conn.execute(
            "SELECT paper_id, citekey, title, year, doi, journal FROM papers WHERE paper_id=?", (paper_id,)
        ).fetchone()
        dg = self._conn.execute("SELECT digest_text FROM digests WHERE paper_id=?", (paper_id,)).fetchone()
        return (
            {
                "paper_id": meta[0], "citekey": meta[1], "title": meta[2], "year": meta[3],
                "doi": meta[4], "journal": meta[5],
            }
            if meta else {},
            dg[0] if dg else "",
        )

    def excerpt(self, paper_id: str, query: str, top: int = 5, max_chars: int = 12000) -> List[dict]:
        q = _fts_query(query)
        rows = self._conn.execute(
            """
            SELECT section, snippet(fulltext_fts, 4, '<<', '>>', '…', 20) AS snip,
                   bm25(fulltext_fts) AS score, length(text) AS n
            FROM fulltext_fts
            WHERE fulltext_fts MATCH ? AND paper_id = ?
            ORDER BY score LIMIT ?
            """,
            (q, paper_id, top),
        ).fetchall()
        return [{"section": r[0], "rank": i + 1, "snippet": r[1], "chars": r[3]} for i, r in enumerate(rows)]

    def search_fulltext(self, query: str, top: int = 10, max_chars: int = 12000) -> List[dict]:
        q = _fts_query(query)
        rows = self._conn.execute(
            """
            SELECT paper_id, citekey, title, section, snippet(fulltext_fts, 4, '<<', '>>', '…', 30) AS snip
            FROM fulltext_fts
            WHERE fulltext_fts MATCH ?
            ORDER BY bm25(fulltext_fts) LIMIT ?
            """,
            (q, top),
        ).fetchall()
        return [
            {"paper_id": r[0], "citekey": r[1], "title": r[2], "section": r[3], "snippet": r[4]}
            for r in rows
        ]

    def stats(self) -> Dict[str, int]:
        out = {}
        for t in ("papers", "digests"):
            out[t] = self._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        out["fulltext_sections"] = self._conn.execute("SELECT COUNT(*) FROM fulltext_fts").fetchone()[0]
        return out


_TYPO_MAP = {
    "‑": "-", "–": "-", "—": "-", "―": "-",
    "‘": "'", "’": "'", "‚": "'",
    "“": '"', "”": '"', "„": '"',
    " ": " ", " ": " ", " ": " ",
    "−": "-", "⁄": "/",
}


def _normalize_for_fts(text: str) -> str:
    """排版连字符/引号等 → ASCII 等价，改善 FTS 匹配（不改动 raw Markdown）。"""
    for a, b in _TYPO_MAP.items():
        text = text.replace(a, b)
    return text


def _fts_query(query: str) -> str:
    """把普通短语转成 FTS5 可用的 OR 查询。"""
    tokens = [t.strip('"') for t in query.split() if t.strip()]
    tokens = [t for t in tokens if len(t) > 1]
    return " OR ".join(f'"{t}"' for t in tokens) if tokens else '""'
