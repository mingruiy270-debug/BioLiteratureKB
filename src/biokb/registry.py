"""Paper Registry：paper_id → record + per-paper 状态。JSON 持久化，简单可靠。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from .models import PaperRecord, PaperState


class Registry:
    def __init__(self, path: Path):
        self.path = path
        self.records: Dict[str, dict] = {}
        self.states: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.records = data.get("records", {})
            self.states = data.get("states", {})
        except Exception:  # noqa: BLE001
            self.records, self.states = {}, {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"records": self.records, "states": self.states}, f, ensure_ascii=False, indent=1)

    def upsert_record(self, rec: PaperRecord) -> None:
        # JSON 重新解析的记录不含 attachment → 合并已保存的 kb_pdf_path
        old = self.records.get(rec.paper_id)
        if old and old.get("attachment", {}).get("kb_pdf_path") and not rec.attachment.kb_pdf_path:
            rec.attachment.kb_pdf_path = old["attachment"]["kb_pdf_path"]
            rec.attachment.source_path = old["attachment"].get("source_path") or rec.attachment.source_path
        self.records[rec.paper_id] = rec.model_dump()
        if rec.paper_id not in self.states:
            self.states[rec.paper_id] = PaperState(paper_id=rec.paper_id).model_dump()

    def get_record(self, paper_id: str) -> Optional[PaperRecord]:
        d = self.records.get(paper_id)
        return PaperRecord(**d) if d else None

    def get_state(self, paper_id: str) -> Optional[PaperState]:
        d = self.states.get(paper_id)
        return PaperState(**d) if d else None

    def set_state(self, state: PaperState) -> None:
        self.states[state.paper_id] = state.model_dump()

    def remove(self, paper_id: str) -> None:
        self.records.pop(paper_id, None)
        self.states.pop(paper_id, None)

    @property
    def paper_ids(self) -> list[str]:
        return list(self.records.keys())
