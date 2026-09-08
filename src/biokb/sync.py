"""同步管线：Zotero JSON → Registry → Inventory → PDF 解析 → 复制 → Markdown → Digest → Index。

Digest 的 LLM 调用支持并发（config digest.concurrency / --concurrency）；
共享状态（registry / SQLite 索引 / report）只在主线程写，保证线程安全。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


@dataclass
class _Prepared:
    """一篇论文完成 PDF→Markdown 后的中间态（digest 待生成）。"""

    rec: PaperRecord
    key: str
    md_text: str
    digest_path: Path
    state: PaperState
    needs_digest: bool = False


def _prepare_paper(
    cfg: Config, registry: Registry, idx: Indexer, client: LLMClient, rec: PaperRecord, inventory: List, report: SyncReport
) -> Optional[_Prepared]:
    """PDF 解析 → Markdown → QC → frontmatter；返回待 digest 的中间态，跳过/失败返回 None。"""
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
        if digest_ok and state.status == "md_ready":
            # digest 已存在（如手动生成）但状态未升级 → 补升级
            state.status = "digest_ready"
            registry.set_state(state)
            registry.save()
        report.markdown["skipped"] += 1
        report.digest["skipped"] += 1
        log_build(cfg.build_log_file, rec.paper_id, "sync", "SKIP", "")
        return None

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
        return None
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
            return None
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
        return None
    add_frontmatter(md_path, {
        "paper_id": rec.paper_id, "citekey": rec.citekey, "title": rec.title, "doi": rec.doi,
        "year": rec.year, "journal": rec.journal, "source_pdf": src.name, "parser": state.parser,
    })
    state.status = "md_ready"

    # ---- Digest 决策（生成在 _finalize_paper，可并发） ----
    if state.digest_version != cfg.digest_version or not digest_ok:
        if state.digest_pending and llm_off:
            # 已标记 pending 且 LLM 仍不可用：不重复尝试
            report.digest["pending"] += 1
            return _Prepared(rec, key, md_text, digest_path, state, needs_digest=False)
        return _Prepared(rec, key, md_text, digest_path, state, needs_digest=True)
    report.digest["skipped"] += 1
    state.status = "digest_ready"
    return _Prepared(rec, key, md_text, digest_path, state, needs_digest=False)


def _generate_job(client: LLMClient, cfg: Config, prepared: _Prepared) -> Tuple[Optional[str], Optional[dict], str]:
    """纯 LLM 调用（无共享状态），供线程池并发执行。"""
    return generate_digest_and_record(client, cfg, prepared.rec, prepared.md_text)


def _finalize_paper(
    cfg: Config, registry: Registry, idx: Indexer, prepared: _Prepared,
    digest_result: Optional[Tuple[Optional[str], Optional[dict], str]], report: SyncReport,
) -> None:
    """写回 digest / 更新状态 / 建索引（仅主线程调用）。"""
    rec, key, md_text, digest_path, state = prepared.rec, prepared.key, prepared.md_text, prepared.digest_path, prepared.state
    if digest_result is not None:
        digest_md, record, dstatus = digest_result
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

    # ---- Index ----
    state.updated_at = now_iso()
    digest_text = ""
    keywords = data_types = methods = ""
    if digest_path.exists():
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


def _process_paper(
    cfg: Config, registry: Registry, idx: Indexer, client: LLMClient, rec: PaperRecord, inventory: List, report: SyncReport
) -> None:
    """单篇串行处理（prepare → digest → finalize）；并发路径见 run_sync。"""
    prepared = _prepare_paper(cfg, registry, idx, client, rec, inventory, report)
    if prepared is None:
        return
    result = _generate_job(client, cfg, prepared) if prepared.needs_digest else None
    _finalize_paper(cfg, registry, idx, prepared, result, report)


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
        # ---- 阶段 1（主线程串行）：PDF → Markdown，收集待 digest 任务 ----
        prepared_list: List[_Prepared] = []
        for rec in records:
            try:
                p = _prepare_paper(cfg, registry, idx, client, rec, entries, report)
                if p is not None:
                    prepared_list.append(p)
            except Exception as e:  # noqa: BLE001
                report.failed.append(FailedEntry(paper_id=rec.paper_id, citekey=rec.citekey, stage="pipeline", error=str(e)[:300], time=now_iso()))
                append_failed(cfg.failed_file, FailedEntry(paper_id=rec.paper_id, citekey=rec.citekey, stage="pipeline", error=str(e)[:300], time=now_iso()))
                log_build(cfg.build_log_file, rec.paper_id, "pipeline", "ERROR", str(e)[:200])
                if not cfg.continue_on_error:
                    break

        # ---- 阶段 2：digest 生成（可并发；纯 LLM 调用，无共享状态） ----
        jobs = [p for p in prepared_list if p.needs_digest]
        results: Dict[str, Tuple[Optional[str], Optional[dict], str]] = {}
        workers = max(1, int(cfg.concurrency))
        if jobs:
            if workers > 1:
                log_build(cfg.build_log_file, "*", "digest", "PARALLEL", f"workers={workers} jobs={len(jobs)}")
                done = 0
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    fut_map = {ex.submit(_generate_job, client, cfg, p): p for p in jobs}
                    for fut in as_completed(fut_map):
                        p = fut_map[fut]
                        done += 1
                        try:
                            results[p.rec.paper_id] = fut.result()
                            log_build(cfg.build_log_file, p.rec.paper_id, "digest", "PROGRESS", f"{done}/{len(jobs)}")
                        except Exception as e:  # noqa: BLE001
                            results[p.rec.paper_id] = (None, None, "failed")
                            log_build(cfg.build_log_file, p.rec.paper_id, "digest", "ERROR", f"{done}/{len(jobs)} {str(e)[:150]}")
            else:
                for p in jobs:
                    try:
                        results[p.rec.paper_id] = _generate_job(client, cfg, p)
                    except Exception as e:  # noqa: BLE001
                        results[p.rec.paper_id] = (None, None, "failed")
                        log_build(cfg.build_log_file, p.rec.paper_id, "digest", "ERROR", str(e)[:150])

        # ---- 阶段 3（主线程串行）：写回 digest / 状态 / 索引 ----
        for p in prepared_list:
            try:
                _finalize_paper(cfg, registry, idx, p, results.get(p.rec.paper_id), report)
            except Exception as e:  # noqa: BLE001
                report.failed.append(FailedEntry(paper_id=p.rec.paper_id, citekey=p.rec.citekey, stage="pipeline", error=str(e)[:300], time=now_iso()))
                append_failed(cfg.failed_file, FailedEntry(paper_id=p.rec.paper_id, citekey=p.rec.citekey, stage="pipeline", error=str(e)[:300], time=now_iso()))
                log_build(cfg.build_log_file, p.rec.paper_id, "pipeline", "ERROR", str(e)[:200])
                if not cfg.continue_on_error:
                    break
    finally:
        idx.close()

    # 清理 failed.json 中已恢复的陈旧条目（仅保留仍处失败态的论文）
    from .state import load_failed

    stale = [f for f in load_failed(cfg.failed_file) if registry.get_state(f["paper_id"]) and registry.get_state(f["paper_id"]).status not in ("failed", "missing", "ambiguous")]
    if stale:
        kept = [f for f in load_failed(cfg.failed_file) if f not in stale]
        cfg.failed_file.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")

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
