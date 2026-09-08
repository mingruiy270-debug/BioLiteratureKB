"""并发 digest 测试：多篇同时生成、线程数受控、状态与产物正确。"""
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

from biokb.config import Config
from biokb.registry import Registry
from biokb.sync import run_sync


def _item(i: int) -> dict:
    return {
        "id": i,
        "type": "article-journal",
        "title": f"Paper number {i} on endometrial receptivity",
        "citation-key": f"paper{i}",
        "container-title": "J Test",
        "DOI": f"10.1000/test{i}",
        "author": [{"family": f"Author{i}", "given": "A"}],
        "issued": {"date-parts": [[2026, 1, 1]]},
    }


class BarrierLLM:
    """chat 阻塞在 barrier 上：只有真正并发才能通过，用于证明并行执行。"""

    def __init__(self, n_expected: int, timeout: float = 5.0):
        self.barrier = threading.Barrier(n_expected, timeout=timeout)
        self.thread_ids = set()
        self.lock = threading.Lock()
        self.max_parallel = 0
        self._active = 0

    def configured(self) -> bool:
        return True

    def chat(self, messages, max_tokens=None) -> str:
        with self.lock:
            self._active += 1
            self.max_parallel = max(self.max_parallel, self._active)
            self.thread_ids.add(threading.get_ident())
        try:
            self.barrier.wait()  # 所有并发任务到齐才继续 → 串行执行会超时
            time.sleep(0.05)
        finally:
            with self.lock:
                self._active -= 1
        return "# 1. 科研故事\n\n## 1.1 研究背景\nconcurrent digest body " * 100

    def chat_json(self, messages, max_tokens=None):
        return {"retrieval_keywords": ["k"], "datasets": [], "computational_workflow": [], "advanced_methods": []}


def _fake_convert(pdf, out_md, priority, mineru_bin=None):
    """替代真实 PDF 解析：写入合法 Markdown。"""
    Path(out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(out_md).write_text("# Abstract\n" + "x" * 2000 + "\n# Results\n" + "y" * 2000, encoding="utf-8")
    return "ok", "pymupdf4llm"


def _setup(tmp_path: Path, n: int) -> Config:
    cfg = Config(root=tmp_path)
    cfg.ensure_dirs()
    cfg.prompts_dir.mkdir(parents=True, exist_ok=True)
    (cfg.prompts_dir / f"paper_digest_{cfg.digest_version}.md").write_text(
        "# 任务\n精读论文并输出 Digest。", encoding="utf-8"
    )
    cfg.zotero_json_dir.mkdir(parents=True, exist_ok=True)
    (cfg.zotero_json_dir / "lib.json").write_text(
        json.dumps([_item(i) for i in range(1, n + 1)]), encoding="utf-8"
    )
    # 预置 PDF + Markdown，使 prepare 阶段无需真实转换
    for i in range(1, n + 1):
        (cfg.pdf_output_dir / f"paper{i}.pdf").write_bytes(b"%PDF-1.4 fake")
        (cfg.md_output_dir / f"paper{i}.md").write_text(
            "# Abstract\n" + "x" * 2000 + "\n# Results\n" + "y" * 2000, encoding="utf-8"
        )
    return cfg


def test_concurrent_digest_generation(tmp_path):
    n = 5
    cfg = _setup(tmp_path, n)
    cfg.concurrency = n
    llm = BarrierLLM(n)
    # prepare 阶段需匹配 PDF：让 resolve_pdf 直接返回预置 PDF
    with patch("biokb.sync.resolve_pdf", side_effect=lambda rec, inv, root: (
        str(cfg.pdf_output_dir / f"{rec.citekey}.pdf"), "matched", []
    )), patch("biokb.sync.LLMClient", return_value=llm), patch(
        "biokb.sync.detect_parsers", return_value=["pymupdf4llm"]
    ), patch("biokb.sync.convert_pdf", side_effect=_fake_convert):
        report = run_sync(cfg, refresh_inventory=False)

    assert report.digest["ready"] == n, report.digest
    assert llm.max_parallel > 1, "未并发执行"
    assert len(llm.thread_ids) > 1, "全部在同一线程"
    for i in range(1, n + 1):
        d = cfg.digest_output_dir / f"paper{i}.md"
        assert d.exists() and "concurrent digest body" in d.read_text(encoding="utf-8")
        st = Registry(cfg.registry_file).get_state(f"10.1000/test{i}")
        assert st.status == "digest_ready" and st.digest_version == cfg.digest_version
    assert report.indexed > 0


def test_concurrency_one_still_works(tmp_path):
    cfg = _setup(tmp_path, 2)
    cfg.concurrency = 1
    llm = BarrierLLM(1)  # 串行：每次只有一个任务，barrier 可立即通过
    with patch("biokb.sync.resolve_pdf", side_effect=lambda rec, inv, root: (
        str(cfg.pdf_output_dir / f"{rec.citekey}.pdf"), "matched", []
    )), patch("biokb.sync.LLMClient", return_value=llm), patch(
        "biokb.sync.detect_parsers", return_value=["pymupdf4llm"]
    ), patch("biokb.sync.convert_pdf", side_effect=_fake_convert):
        report = run_sync(cfg, refresh_inventory=False)
    assert report.digest["ready"] == 2
    assert llm.max_parallel == 1


def test_digest_failure_isolated_in_concurrent_run(tmp_path):
    """一篇失败不影响其他篇，且失败态被正确记录。"""
    cfg = _setup(tmp_path, 3)
    cfg.concurrency = 3

    class FlakyLLM(BarrierLLM):
        def chat(self, messages, max_tokens=None) -> str:
            if "number 2" in messages[-1]["content"]:
                self.barrier.wait()  # 仍需参与 barrier，避免其他线程等待超时
                raise RuntimeError("boom")
            return super().chat(messages, max_tokens)

    llm = FlakyLLM(3)
    with patch("biokb.sync.resolve_pdf", side_effect=lambda rec, inv, root: (
        str(cfg.pdf_output_dir / f"{rec.citekey}.pdf"), "matched", []
    )), patch("biokb.sync.LLMClient", return_value=llm), patch(
        "biokb.sync.detect_parsers", return_value=["pymupdf4llm"]
    ), patch("biokb.sync.convert_pdf", side_effect=_fake_convert):
        report = run_sync(cfg, refresh_inventory=False)
    assert report.digest["ready"] == 2
    reg = Registry(cfg.registry_file)
    assert reg.get_state("10.1000/test2").status == "md_ready"
