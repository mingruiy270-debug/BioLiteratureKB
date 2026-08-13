"""Pydantic 数据模型。保持轻量，不做巨型 ontology。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Author(BaseModel):
    family: str = ""
    given: str = ""


class AttachmentInfo(BaseModel):
    zotero_attachment_key: Optional[str] = None
    original_filename: str = ""
    source_path: str = ""
    kb_pdf_path: str = ""


class PaperRecord(BaseModel):
    paper_id: str
    citekey: str = ""
    zotero_item_key: str = ""
    title: str = ""
    doi: str = ""
    pmid: str = ""
    year: Optional[int] = None
    authors: List[str] = Field(default_factory=list)
    journal: str = ""
    url: str = ""
    abstract: str = ""
    attachment: AttachmentInfo = Field(default_factory=AttachmentInfo)


class InventoryEntry(BaseModel):
    path: str
    folder: str
    filename: str
    normalized_stem: str
    size: int
    mtime: float


class PaperState(BaseModel):
    paper_id: str
    pdf_sha256: str = ""
    parser: str = ""
    digest_version: str = ""
    digest_pending: bool = False  # LLM 未配置时标记，避免每次 sync 重复尝试
    status: str = "new"  # new | pdf_ready | md_ready | digest_ready | pdf_missing | pdf_ambiguous | failed
    updated_at: str = ""


class FailedEntry(BaseModel):
    paper_id: str
    citekey: str
    stage: str
    error: str
    time: str


class DigestRecord(BaseModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)
    research_story: Dict[str, Any] = Field(default_factory=dict)
    datasets: List[Dict[str, Any]] = Field(default_factory=list)
    computational_workflow: List[Dict[str, Any]] = Field(default_factory=list)
    machine_learning: List[Dict[str, Any]] = Field(default_factory=list)
    advanced_methods: List[Dict[str, Any]] = Field(default_factory=list)
    wet_experiments: List[Dict[str, Any]] = Field(default_factory=list)
    dry_wet_integration: List[Dict[str, Any]] = Field(default_factory=list)
    figure_map: List[str] = Field(default_factory=list)
    author_reported_limitations: List[str] = Field(default_factory=list)
    retrieval_keywords: List[str] = Field(default_factory=list)
