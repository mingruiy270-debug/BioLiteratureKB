"""Paper Digest 管线：精读 → Digest Markdown → 结构化 Record。

长文（超过 max_chars_per_call）按 section 分批精读后合成。
LLM 未配置时状态为 DIGEST_PENDING，后续可补跑。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .llm_client import LLMClient, LLMNotConfigured
from .markdown_parser import split_sections
from .models import DigestRecord, PaperRecord

SYSTEM_ROLE = (
    "You are a rigorous biomedical paper analyst. Follow the task instructions exactly. "
    "Output only the requested content, in the specified format. Do not add commentary."
)


def _load_prompt(cfg: Config) -> str:
    p = cfg.prompts_dir / f"paper_digest_{cfg.digest_version}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _meta_block(rec: PaperRecord, cfg: Config) -> str:
    return json.dumps(
        {
            "paper_id": rec.paper_id,
            "citekey": rec.citekey,
            "title": rec.title,
            "year": rec.year,
            "doi": rec.doi,
            "journal": rec.journal,
            "authors": rec.authors[:5],
        },
        ensure_ascii=False,
    )


def _part_extract(client: LLMClient, prompt: str, meta: str, part_name: str, text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_ROLE},
        {"role": "user", "content": f"任务：{prompt}\n\n论文元数据：\n{meta}\n\n论文片段（{part_name}）：\n{text}"},
    ]
    return client.chat(messages)


def _synthesize(client: LLMClient, prompt: str, meta: str, parts: List[Dict[str, str]]) -> str:
    joined = "\n\n=====PART=====\n\n".join(f"[{p['name']}]\n{p['text']}" for p in parts)
    messages = [
        {"role": "system", "content": SYSTEM_ROLE},
        {"role": "user", "content": f"任务：{prompt}\n\n论文元数据：\n{meta}\n\n以下是该论文按 section 分批提取的内容。请基于这些内容（它们覆盖了论文全文），输出该论文完整的 Paper Digest（Digest 结构按任务要求）：\n\n{joined[:200_000]}"},
    ]
    return client.chat(messages)


def build_digest(
    client: LLMClient, cfg: Config, rec: PaperRecord, md_text: str
) -> Optional[str]:
    """返回 Digest Markdown；失败返回 None。"""
    prompt = _load_prompt(cfg)
    meta = _meta_block(rec, cfg)
    if not prompt or not meta:
        return None
    if len(md_text) <= cfg.max_chars_per_call:
        return _part_extract(client, prompt, meta, "全文", md_text)
    sections = split_sections(md_text)
    parts: List[Dict[str, str]] = []
    buf, size = [], 0
    for name, text in sections:
        buf.append(text)
        size += len(text)
        if size >= cfg.max_chars_per_call:
            parts.append({"name": name, "text": "\n\n".join(buf)})
            buf, size = [], 0
    if buf:
        parts.append({"name": sections[-1][0], "text": "\n\n".join(buf)})
    extracted = []
    for p in parts:
        out = _part_extract(client, prompt, meta, p["name"], p["text"])
        extracted.append({"name": p["name"], "text": out})
    return _synthesize(client, prompt, meta, extracted)


_RECORD_PROMPT = """根据 Paper Digest 提取结构化 JSON Record。Schema:

{
  "metadata": {},
  "research_story": {"background": "", "knowledge_gap": "", "scientific_question": "", "hypothesis": "", "storyline": [], "main_conclusions": []},
  "datasets": [{"source": "", "data_type": "", "species": "", "cohort": "", "purpose": ""}],
  "computational_workflow": [{"step": 1, "input": "", "data_type": "", "data_source": "", "method": "", "tool": "", "purpose": "", "result": "", "interpretation": "", "role_in_next_step": ""}],
  "machine_learning": [{"task": "", "features": "", "labels": "", "sample_size": "", "train_cohort": "", "test_cohort": "", "external_validation": "", "split": "", "algorithms": "", "metrics": "", "notable": ""}],
  "advanced_methods": [{"name": "", "category": "", "input": "", "output": "", "problem_solved": "", "role": ""}],
  "wet_experiments": [{"experiment": "", "object": "", "intervention": "", "method": "", "result": "", "conclusion": ""}],
  "dry_wet_integration": [{"dry_step": "", "wet_step": "", "relationship": "", "supported_conclusion": ""}],
  "figure_map": [],
  "author_reported_limitations": [],
  "retrieval_keywords": []
}

事实纪律：未报告 → "not_reported"；不清楚 → "unclear"；不存在 → null。只输出 JSON，不要输出其他内容。"""


def build_record(client: LLMClient, rec: PaperRecord, digest_md: str) -> Dict[str, Any]:
    """从 Digest 提取结构化 Record；失败则回退到元数据级 Record。"""
    try:
        messages = [
            {"role": "system", "content": SYSTEM_ROLE},
            {"role": "user", "content": f"{_RECORD_PROMPT}\n\n论文元数据：\n{_meta_block(rec, client.cfg)}\n\nPaper Digest：\n{digest_md[:120_000]}"},
        ]
        data = client.chat_json(messages)
        if data and isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return _fallback_record(rec)


def _fallback_record(rec: PaperRecord) -> Dict[str, Any]:
    """元数据级回退 Record（LLM 提取失败时使用）。"""
    return DigestRecord(
        metadata={"title": rec.title, "year": rec.year, "doi": rec.doi, "journal": rec.journal, "authors": rec.authors},
        research_story={"scientific_question": "not_reported", "hypothesis": "not_reported"},
        retrieval_keywords=[w for w in re.split(r"[\s,;，；]+", rec.title.lower()) if len(w) > 3][:10],
    ).model_dump()


def write_digest(cfg: Config, rec: PaperRecord, digest_md: str, record: Dict[str, Any]) -> None:
    cfg.digest_output_dir.mkdir(parents=True, exist_ok=True)
    cfg.record_dir.mkdir(parents=True, exist_ok=True)
    (cfg.digest_output_dir / f"{rec.citekey or rec.paper_id}.md").write_text(digest_md, encoding="utf-8")
    (cfg.record_dir / f"{rec.citekey or rec.paper_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def generate_digest_and_record(
    client: LLMClient, cfg: Config, rec: PaperRecord, md_text: str
) -> tuple[Optional[str], Optional[Dict[str, Any]], str]:
    """返回 (digest_md, record, status)。status ∈ ready | pending | failed"""
    try:
        digest_md = build_digest(client, cfg, rec, md_text)
        if not digest_md:
            return None, None, "failed"
        record = build_record(client, rec, digest_md)
        return digest_md, record, "ready"
    except LLMNotConfigured:
        return None, None, "pending"
    except Exception:  # noqa: BLE001
        return None, None, "failed"
