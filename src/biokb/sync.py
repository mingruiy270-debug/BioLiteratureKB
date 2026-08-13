"""同步管线：Zotero JSON → Registry → Inventory → PDF 解析 → 复制 → Markdown → Digest → Index。"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .config import Config
from .converter import add_frontmatter, convert_pdf, detect_parsers
from .digest import generate_digest_and_record, write_digest
from .indexer import Indexer
from .llm_client import LLMClient
from .markdown_parser import qc_check
from .models import FailedEntry, PaperRecord, PaperState
from .pdf_inventory import load_inventory, save_inventory, scan_storage
from .pdf_resolver import resolve_pdf
from .registry import Registry
from .state import append_failed, load_state, log_build, now_iso, save_state
from .zotero import parse_all


@dataclass
class SyncReport:
    zotero_items: int = 0
    unique_papers: int = 0
    duplicates: int = 0
    pdf_status: dict = field(default_factory=lambda: {"matched": 0, "ambiguous": 0, "missing": 0})
    markdown: dict = field(default_factory=lambda: {"ok": 0, "failed": 0, "skipped": 0})
    digest: dict = field(default_factory=lambda: {"ready": 0, "pending": 0, "failed": 0, "skipped": 0})
    indexed: int = 0
    failed: List[FailedEntry] = field(default_factory=list)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _record_key(rec: PaperRecord) -> str:
    return rec.citekey or rec.paper_id


def _process_paper(
    cfg: Config, registry: Registry, idx: Indexer, client: LLMClient, rec: PaperRecord, inventory: List, report: SyncReport
) -> None:
    key = _record_key(rec)
    state = registry.get_state(rec.paper_id) or PaperState(paper_id=rec.paper_id)
    # JSON 重新解析的记录无 attachment → 合并 registry 中已保存的 PDF 路径
    stored = registry.get_record(rec.paper_id)
    if stored and stored.attachment.kb_pdf_path:
        rec.attachment.kb_pdf_path = stored.attachment.kb_pdf_path
        rec.attachment.source_path = stored.attachment.source_path or rec.attachment.source_path
    md_path = cfg.md_output_dir / f"{key}.md"
    digest_path = cfg.digest_output_dir / f"{key}.md"
    digest_ok = digest_path.exists()

    # ---- 快速跳过：产物齐全且未变化（不做任何模糊匹配） ----
    kb_pdf = Path(rec.attachment.kb_pdf_path) if rec.attachment.kb_pdf_path else None
    llm_off = not client.configured()
    if (
        state.status in ("digest_ready", "md_ready")
        and state.digest_version == cfg.digest_version
        and kb_pdf and kb_pdf.exists()
        and md_path.exists()
        and (digest_ok or (state.digest_pending and llm_off))
        and _sha256(kb_pdf) == state.pdf_sha256
        and idx.has_paper(rec.paper_id)  # 索引缺失（如 db 重建）→ 不跳过，自愈重索引
    ):
        report.markdown["skipped"] += 1
        report.digest["skipped"] += 1
        log_build(cfg.build_log_file, rec.paper_id, "sync", "SKIP", "")
        return

    # ---- PDF 解析与复制 ----
    path, status, _ = resolve_pdf(rec, inventory, cfg.zotero_storage_root)
    report.pdf_status[status] = report.pdf_status.get(status, 0) + 1
    if status != "matched":
        state.status = status
        registry.set_state(state)
        registry.save()
        if status == "ambiguous":
            append_failed(cfg.failed_file, FailedEntry(paper_id=rec.paper_id, citekey=rec.citekey, stage="pdf", error="PDF_AMBIGUOUS", time=now_iso()))
        log_build(cfg.build_log_file, rec.paper_id, "pdf", status.upper(), "")
        return
    src = Path(path)
    dst = cfg.pdf_output_dir / f"{key}.pdf"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    rec.attachment.kb_pdf_path = str(dst)
    rec.attachment.source_path = str(src)
    registry.upsert_record(rec)
    state.status = "pdf_ready"

    # ---- PDF → Markdown（PDF 变化或 Markdown 缺失时重新转换） ----
    sha_now = _sha256(dst)
    pdf_changed = state.pdf_sha256 != sha_now
    state.pdf_sha256 = sha_now
    if pdf_changed or not md_path.exists():
        status_md, parser_used = convert_pdf(dst, md_path, cfg.parser_priority, cfg.mineru_bin)
        if status_md != "ok":
            report.markdown["failed"] += 1
            state.status = "failed"
            registry.set_state(state)
            registry.save()
            append_failed(cfg.failed_file, FailedEntry(paper_id=rec.paper_id, citekey=rec.citekey, stage="markdown", error="convert failed", time=now_iso()))
            log_build(cfg.build_log_file, rec.paper_id, "markdown", "FAILED", parser_used or "no parser")
            return
        state.parser = parser_used
        report.markdown["ok"] += 1
        log_build(cfg.build_log_file, rec.paper_id, "markdown", "OK", parser_used)
    else:
        report.markdown["skipped"] += 1

    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    ok_qc, reason = qc_check(md_text)
    if not ok_qc:
        report.markdown["failed"] += 1
        state.status = "failed"
        registry.set_state(state)
        registry.save()
        append_failed(cfg.failed_file, FailedEntry(paper_id=rec.paper_id, citekey=rec.citekey, stage="qc", error=f"qc_fail:{reason}", time=now_iso()))
        log_build(cfg.build_log_file, rec.paper_id, "qc", "FAILED", reason)
        return
    add_frontmatter(md_path, {
        "paper_id": rec.paper_id, "citekey": rec.citekey, "title": rec.title, "doi": rec.doi,
        "year": rec.year, "journal": rec.journal, "source_pdf": src.name, "parser": state.parser,
    })
    state.status = "md_ready"

    # ---- Digest（仅在版本变化或缺失时） ----
    if state.digest_version != cfg.digest_version or not digest_ok:
        if state.digest_pending and llm_off:
            # 已标记 pending 且 LLM 仍不可用：不重复尝试
            report.digest["pending"] += 1
        else:
            digest_md, record, dstatus = generate_digest_and_record(client, cfg, rec, md_text)
            if dstatus == "ready" and digest_md and record:
                write_digest(cfg, rec, digest_md, record)
                state.digest_version = cfg.digest_version
                state.digest_pending = False
                state.status = "digest_ready"
                report.digest["ready"] += 1
                log_build(cfg.build_log_file, rec.paper_id, "digest", "OK", "")
            elif dstatus == "pending":
                state.status = "md_ready"
                state.digest_version = cfg.digest_version
                state.digest_pending = True
                report.digest["pending"] += 1
                log_build(cfg.build_log_file, rec.paper_id, "digest", "PENDING", "LLM not configured")
            else:
                state.status = "md_ready"
                state.digest_pending = False
                report.digest["failed"] += 1
                append_failed(cfg.failed_file, FailedEntry(paper_id=rec.paper_id, citekey=rec.citekey, stage="digest", error="llm failed", time=now_iso()))
                log_build(cfg.build_log_file, rec.paper_id, "digest", "FAILED", "")
    else:
        report.digest["skipped"] += 1
        state.status = "digest_ready"

    # ---- Index ----
    state.updated_at = now_iso()
    digest_text = ""
    keywords = data_types = methods = ""
    if digest_ok or digest_path.exists():
        digest_text = digest_path.read_text(encoding="utf-8", errors="replace")
    record_file = cfg.record_dir / f"{key}.json"
    if record_file.exists():
        try:
            recj = json.loads(record_file.read_text(encoding="utf-8"))
            keywords = ",".join(recj.get("retrieval_keywords", []))
            data_types = ",".join(str(d.get("data_type", "")) for d in recj.get("datasets", []))
            methods = ",".join(str(w.get("method", "")) for w in recj.get("computational_workflow", []))
            methods += "," + ",".join(str(m.get("name", "")) for m in recj.get("advanced_methods", []))
        except Exception:  # noqa: BLE001
            pass
    idx.upsert_digest(rec.paper_id, digest_text, keywords, data_types, methods)
    n_sec = idx.replace_fulltext(rec.paper_id, rec.citekey, rec.title, md_text)
    report.indexed += n_sec
    idx.upsert_paper(rec, state.status, state.digest_version)
    registry.set_state(state)
    registry.save()
    log_build(cfg.build_log_file, rec.paper_id, "index", "OK", f"sections={n_sec}")


def run_sync(cfg: Config, refresh_inventory: bool = False) -> SyncReport:
    cfg.ensure_dirs()
    report = SyncReport()

    records, dup = parse_all(cfg.zotero_json_dir)
    report.zotero_items = len(records) + dup
    report.unique_papers = len(records)
    report.duplicates = dup

    registry = Registry(cfg.registry_file)
    for rec in records:
        registry.upsert_record(rec)
    registry.save()

    # 自动增量刷新：JSON 更新（比 inventory 新）或 storage 有新 PDF → 重扫
    def _json_newest_mtime() -> float:
        mt = 0.0
        if cfg.zotero_json_dir.exists():
            for fp in cfg.zotero_json_dir.glob("*.json"):
                try:
                    mt = max(mt, fp.stat().st_mtime)
                except OSError:
                    pass
        return mt

    inv_mtime = cfg.pdf_inventory_file.stat().st_mtime if cfg.pdf_inventory_file.exists() else 0.0
    if refresh_inventory or not cfg.pdf_inventory_file.exists() or _json_newest_mtime() > inv_mtime:
        entries = scan_storage(cfg.zotero_storage_root)
        save_inventory(cfg.pdf_inventory_file, entries)
        log_build(cfg.build_log_file, "*", "inventory", "REFRESH", f"{len(entries)} pdfs (json updated or --refresh)")
    else:
        entries = load_inventory(cfg.pdf_inventory_file)
        if not entries:
            entries = scan_storage(cfg.zotero_storage_root)
            save_inventory(cfg.pdf_inventory_file, entries)

    idx = Indexer(cfg.index_db)
    client = LLMClient(cfg)
    parsers = detect_parsers(cfg.mineru_bin)
    log_build(cfg.build_log_file, "*", "sync", "START", f"parsers={parsers} llm={'SET' if client.configured() else 'MISSING'}")

    try:
        for rec in records:
            try:
                _process_paper(cfg, registry, idx, client, rec, entries, report)
            except Exception as e:  # noqa: BLE001
                report.failed.append(FailedEntry(paper_id=rec.paper_id, citekey=rec.citekey, stage="pipeline", error=str(e)[:300], time=now_iso()))
                append_failed(cfg.failed_file, FailedEntry(paper_id=rec.paper_id, citekey=rec.citekey, stage="pipeline", error=str(e)[:300], time=now_iso()))
                log_build(cfg.build_log_file, rec.paper_id, "pipeline", "ERROR", str(e)[:200])
                if not cfg.continue_on_error:
                    break
    finally:
        idx.close()

    state = load_state(cfg.state_file)
    state["last_sync"] = now_iso()
    state["report"] = {
        "zotero_items": report.zotero_items, "unique_papers": report.unique_papers,
        "pdf_status": report.pdf_status, "markdown": report.markdown,
        "digest": report.digest, "indexed": report.indexed,
    }
    save_state(cfg.state_file, state)
    log_build(cfg.build_log_file, "*", "sync", "DONE", "")
    return report
