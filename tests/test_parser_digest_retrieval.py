"""Markdown QC/section、Digest (mock LLM)、Retrieval 全链路测试。"""
import json
from pathlib import Path

import pytest

from biokb.config import Config
from biokb.digest import build_record, generate_digest_and_record
from biokb.indexer import Indexer
from biokb.markdown_parser import qc_check, split_sections
from biokb.models import PaperRecord
from biokb.retrieval import Retrieval


# ---------------- Markdown QC / sections ----------------

def test_qc_empty_and_short():
    assert qc_check("")[0] is False
    assert qc_check("short text")[0] is False
    ok, reason = qc_check("x" * 2000)
    assert not ok and reason in ("too_short(2000)", "no_known_sections")


def test_qc_ok():
    md = "# Abstract\nSome abstract text.\n\n# Introduction\n" + "text " * 2000
    ok, reason = qc_check(md)
    assert ok, reason


def test_split_sections_headings():
    md = "# Abstract\nabstract body\n\n# Methods\nmethods body\n\n# Results\nresults body\n\n## Single-cell analysis\nsc body"
    sections = split_sections(md)
    names = [s[0] for s in sections]
    assert "Abstract" in names and "Methods" in names
    assert sum(len(t) for _, t in sections) == 44  # 正文总长（不含 heading 文本）


def test_split_sections_no_headings():
    md = "\n\n".join([f"paragraph {i} " + "x" * 1000 for i in range(10)])
    sections = split_sections(md)
    assert len(sections) >= 2
    assert all(name.startswith("chunk_") for name, _ in sections)


# ---------------- Digest（mock LLM） ----------------

class FakeLLM:
    def __init__(self, cfg, behavior="ok"):
        self.cfg = cfg
        self.behavior = behavior
        self.calls = 0

    def configured(self):
        return True

    def chat(self, messages, max_tokens=8000):
        self.calls += 1
        if self.behavior == "malformed":
            raise RuntimeError("boom")
        return "# 1. 科研故事\n\n## 1.1 研究背景\nmock digest " * 200

    def chat_json(self, messages, max_tokens=8000):
        if self.behavior == "ok":
            return {
                "metadata": {"title": "t"},
                "research_story": {"scientific_question": "q", "hypothesis": "not_explicitly_stated"},
                "datasets": [{"source": "GSE123", "data_type": "scRNA-seq", "purpose": "discovery"}],
                "computational_workflow": [{"step": 1, "method": "CellChat", "purpose": "communication"}],
                "wet_experiments": [],
                "retrieval_keywords": ["endometrium", "receptivity"],
            }
        if self.behavior == "malformed-json":
            return None
        return None


@pytest.fixture
def cfg(tmp_path):
    c = Config(root=tmp_path)
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "paper_digest_v1.md").write_text(
        "# 任务\n精读论文并输出 Digest。", encoding="utf-8"
    )
    return c


@pytest.fixture
def rec():
    return PaperRecord(
        paper_id="10.1/abc", citekey="testPaper", title="Test paper on endometrial receptivity",
        year=2025, doi="10.1/abc", journal="Test J", authors=["Zhang Wei"],
    )


def test_digest_ok_and_record(cfg, rec):
    client = FakeLLM(cfg, "ok")
    md_text = "# Abstract\n" + "y" * 3000
    digest_md, record, status = generate_digest_and_record(client, cfg, rec, md_text)
    assert status == "ready" and digest_md and record
    assert record["retrieval_keywords"] == ["endometrium", "receptivity"]


def test_digest_malformed_record_falls_back(cfg, rec):
    client = FakeLLM(cfg, "malformed-json")
    digest_md, record, status = generate_digest_and_record(client, cfg, rec, "x" * 3000)
    assert status == "ready"
    assert "retrieval_keywords" in record  # fallback record（含标题关键词）
    assert client.calls == 1  # digest 成功，record 直接回退


def test_digest_llm_failure(cfg, rec):
    client = FakeLLM(cfg, "malformed")
    digest_md, record, status = generate_digest_and_record(client, cfg, rec, "x" * 3000)
    assert status == "failed"


def test_long_paper_section_synthesis(cfg, rec):
    client = FakeLLM(cfg, "ok")
    cfg.max_chars_per_call = 500
    md_text = "# Abstract\n" + "a" * 800 + "\n# Methods\n" + "b" * 800 + "\n# Results\n" + "c" * 800
    digest_md, _, status = generate_digest_and_record(client, cfg, rec, md_text)
    assert status == "ready"
    assert client.calls >= 4  # 3 部分提取 + 1 合成


def test_build_record_not_reported(cfg, rec):
    client = FakeLLM(cfg, "ok")
    r = build_record(client, rec, "# 1. 科研故事\n")
    assert r["research_story"]["hypothesis"] == "not_explicitly_stated"


# ---------------- Retrieval 全链路 ----------------

def _make_paper(idx: Indexer, pid: str, citekey: str, title: str, md: str):
    rec = PaperRecord(paper_id=pid, citekey=citekey, title=title, year=2026, journal="J")
    idx.upsert_paper(rec, "digest_ready", "v1")
    idx.upsert_digest(pid, f"Digest about {title}. CellChat intercellular communication.", "endometrium,cellchat", "scRNA-seq", "CellChat")
    idx.replace_fulltext(pid, citekey, title, md)


@pytest.fixture
def idx(tmp_path):
    return Indexer(tmp_path / "test.sqlite")


def test_search_digest_excerpt_chain(idx):
    md = (
        "# Abstract\nDecidual natural killer cells mediate vascular remodeling.\n"
        "# Methods\nCellChat v2 was used for ligand-receptor analysis.\n"
        "# Results\nMacrophage to fibroblast TGFB1 signaling was enhanced.\n" + "x" * 1500
    )
    _make_paper(idx, "10.1/a", "paperA", "Single-cell dissection of the decidua", md)

    hits = idx.search("cell communication", top=5)
    assert hits and hits[0]["paper_id"] == "10.1/a"

    meta, digest_text = idx.get_digest("10.1/a")
    assert "CellChat" in digest_text

    ex = idx.excerpt("10.1/a", "CellChat ligand receptor", top=3)
    assert ex and ex[0]["section"] == "Methods"

    ft = idx.search_fulltext("decidual natural killer", top=5)
    assert ft and ft[0]["section"] == "Abstract"


def test_retrieval_alias_citekey(idx):
    md = "# Abstract\n" + "y" * 1500
    _make_paper(idx, "10.1/b", "aliasPaper", "Alias paper", md)
    r = Retrieval.__new__(Retrieval)  # 仅测试别名解析
    from biokb.retrieval import _resolve_alias
    assert _resolve_alias(idx.db_path, "aliasPaper") == "10.1/b"
