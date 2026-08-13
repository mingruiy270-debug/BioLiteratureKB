"""增量同步测试：SKIP 规则、digest_version 变化、registry 合并。"""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from biokb.config import Config
from biokb.models import AttachmentInfo, PaperRecord, PaperState
from biokb.registry import Registry
from biokb.sync import _process_paper


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mk_pdf(p: Path, content: bytes = b"%PDF-1.4 fake") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


class FakeIndexer:
    def __init__(self):
        self.fulltext = 0

    def upsert_digest(self, *a):
        pass

    def upsert_paper(self, *a):
        pass

    def replace_fulltext(self, *a):
        self.fulltext += 1
        return 3

    def has_paper(self, paper_id: str) -> bool:
        return True


class NoopLLM:
    def configured(self):
        return False


class Report:
    def __init__(self):
        self.pdf_status = {"matched": 0, "ambiguous": 0, "missing": 0}
        self.markdown = {"ok": 0, "failed": 0, "skipped": 0}
        self.digest = {"ready": 0, "pending": 0, "failed": 0, "skipped": 0}
        self.indexed = 0


def _ready_setup(tmp_path: Path):
    """构造一篇完整就绪（digest_ready）的论文。"""
    cfg = Config(root=tmp_path)
    cfg.ensure_dirs()
    rec = PaperRecord(
        paper_id="10.1/abc", citekey="readyPaper", title="Ready paper", doi="10.1/abc",
        year=2026, journal="J",
        attachment=AttachmentInfo(kb_pdf_path=str(cfg.pdf_output_dir / "readyPaper.pdf")),
    )
    kb = _mk_pdf(cfg.pdf_output_dir / "readyPaper.pdf")
    (cfg.md_output_dir / "readyPaper.md").write_text("# Abstract\n" + "x" * 2000, encoding="utf-8")
    (cfg.digest_output_dir / "readyPaper.md").write_text("# digest\n", encoding="utf-8")
    (cfg.record_dir / "readyPaper.json").write_text(json.dumps({"retrieval_keywords": []}), encoding="utf-8")
    reg = Registry(cfg.registry_file)
    reg.upsert_record(rec)
    reg.set_state(PaperState(
        paper_id=rec.paper_id, pdf_sha256=_sha(kb), parser="pymupdf4llm",
        digest_version=cfg.digest_version, status="digest_ready", updated_at="t",
    ))
    reg.save()
    return cfg, rec


def test_ready_paper_skips_without_fuzzy(tmp_path):
    cfg, rec = _ready_setup(tmp_path)
    report = Report()
    with patch("biokb.sync.resolve_pdf") as mock_resolve:
        _process_paper(cfg, Registry(cfg.registry_file), FakeIndexer(), NoopLLM(), rec, [], report)
        mock_resolve.assert_not_called()  # 快速跳过：不做模糊匹配
    assert report.markdown["skipped"] == 1 and report.digest["skipped"] == 1


def test_digest_version_bump_redoes_digest_not_markdown(tmp_path):
    cfg, rec = _ready_setup(tmp_path)
    cfg.digest_version = "v2"  # 模拟升级精读提示词
    report = Report()

    with patch("biokb.sync.resolve_pdf", return_value=(str(cfg.pdf_output_dir / "readyPaper.pdf"), "matched", [])), \
         patch("biokb.sync.convert_pdf") as mock_conv, \
         patch("biokb.sync.generate_digest_and_record") as mock_gen:
        mock_gen.return_value = ("# new digest v2", {"retrieval_keywords": ["k"]}, "ready")
        _process_paper(cfg, Registry(cfg.registry_file), FakeIndexer(), NoopLLM(), rec, [], report)

    mock_conv.assert_not_called()  # Markdown 不重转（add_frontmatter 首次添加 frontmatter 除外）
    assert mock_gen.called  # Digest 重新生成
    assert report.digest["ready"] == 1
    md = (cfg.md_output_dir / "readyPaper.md").read_text(encoding="utf-8")
    assert "x" * 2000 in md  # 正文未被重写


def test_registry_merge_keeps_kb_path(tmp_path):
    cfg, rec = _ready_setup(tmp_path)
    fresh = rec.model_copy(deep=True)
    fresh.attachment = AttachmentInfo()  # 模拟 JSON 重新解析（无 attachment）
    reg = Registry(cfg.registry_file)
    reg.upsert_record(fresh)
    assert reg.get_record(rec.paper_id).attachment.kb_pdf_path == str(cfg.pdf_output_dir / "readyPaper.pdf")


def test_missing_pdf_marks_state(tmp_path):
    cfg = Config(root=tmp_path)
    cfg.ensure_dirs()
    rec = PaperRecord(paper_id="10.1/nope", citekey="noPdf", title="No pdf paper", doi="10.1/nope")
    report = Report()
    with patch("biokb.sync.resolve_pdf", return_value=(None, "missing", [])):
        _process_paper(cfg, Registry(cfg.registry_file), FakeIndexer(), NoopLLM(), rec, [], report)
    assert report.pdf_status["missing"] == 1
    assert Registry(cfg.registry_file).get_state(rec.paper_id).status == "missing"
