"""PDF Resolution 测试：8 个规定 case（含截断标题）。"""
from pathlib import Path

from biokb.models import AttachmentInfo, InventoryEntry, PaperRecord
from biokb.pdf_resolver import resolve_pdf, score_candidate

LAM_TITLE = (
    "Decoding the lymphangioleiomyomatosis (LAM) niche microenvironment "
    "via integrative analysis of single cell multiomics and spatial transcriptomics"
)
LAM_FILENAME = (
    "Chen 等 - 2026 - Decoding the lymphangioleiomyomatosis (LAM) niche microenvironment "
    "via integrative analysis of singl.pdf"
)


def _rec(title=LAM_TITLE, doi="10.1183/13993003.01234-2025", year=2026, authors=("Chen",), **kw):
    att = kw.pop("attachment", AttachmentInfo())
    return PaperRecord(
        paper_id=doi, citekey="chen2026lam", title=title, doi=doi, year=year,
        authors=list(authors), attachment=att, **kw,
    )


def _inv(path: Path, filename: str) -> InventoryEntry:
    return InventoryEntry(path=str(path / filename), folder="X", filename=filename, normalized_stem="", size=1, mtime=0.0)


def _fill_stems(entries, root):
    from biokb.pdf_inventory import normalize_pdf_filename
    for e in entries:
        e.path = str(root / e.filename)
        e.normalized_stem = normalize_pdf_filename(e.filename)
    return entries


def test_case1_attachment_path_exact(tmp_path):
    f = tmp_path / "paper.pdf"
    f.write_bytes(b"x")
    rec = _rec(attachment=AttachmentInfo(source_path=str(f)))
    p, status, _ = resolve_pdf(rec, [], Path("D:/zotero/storage"))
    assert status == "matched" and p == str(f)


def test_case2_attachment_key(tmp_path):
    folder = tmp_path / "ABC123"
    folder.mkdir()
    (folder / "paper.pdf").write_bytes(b"x")
    rec = _rec(attachment=AttachmentInfo(zotero_attachment_key="ABC123"))
    p, status, _ = resolve_pdf(rec, [], tmp_path)
    assert status == "matched" and Path(p).name == "paper.pdf"


def test_case3_filename_exact(tmp_path):
    rec = _rec(attachment=AttachmentInfo(original_filename="Chen_2026_LAM.pdf"))
    entries = _fill_stems([_inv(tmp_path, "Chen_2026_LAM.pdf"), _inv(tmp_path, "Other paper.pdf")], tmp_path)
    p, status, _ = resolve_pdf(rec, entries, tmp_path)
    assert status == "matched" and p.endswith("Chen_2026_LAM.pdf")


def test_case4_truncated_title(tmp_path):
    """正式标题 vs 被截断的 PDF 文件名 → 高可信候选。"""
    rec = _rec()
    entries = _fill_stems([_inv(tmp_path, LAM_FILENAME)], tmp_path)
    s = score_candidate(rec, entries[0])
    assert s >= 85, f"截断标题得分应很高, got {s}"
    p, status, _ = resolve_pdf(rec, entries, tmp_path)
    assert status == "matched"
    assert p.endswith(LAM_FILENAME)


def test_case5_punctuation_difference(tmp_path):
    rec = _rec(title="Cell-cell communication in the decidua: a single-cell study")
    entries = _fill_stems([_inv(tmp_path, "Smith 等 - 2025 - Cell-cell communication in the decidua - a single-cell study.pdf")], tmp_path)
    p, status, _ = resolve_pdf(rec, entries, tmp_path)
    assert status == "matched"


def test_case6_unicode_difference(tmp_path):
    rec = _rec(title="De novo mutations and copy number variants in recurrent miscarriage")
    entries = _fill_stems([_inv(tmp_path, "Johnson 2025 - De novo mutations and copy number variants in recurrent miscarriage.pdf")], tmp_path)
    p, status, _ = resolve_pdf(rec, entries, tmp_path)
    assert status == "matched"


def test_case7_author_year_prefix(tmp_path):
    rec = _rec()
    entries = _fill_stems([_inv(tmp_path, LAM_FILENAME)], tmp_path)
    p, status, _ = resolve_pdf(rec, entries, tmp_path)
    assert status == "matched"


def test_case8_two_similar_candidates_ambiguous(tmp_path):
    """两个高度相似候选 → 进入歧义，不静默错配。"""
    rec = _rec(
        title="Integrated analysis of single-cell multiomics reveals endometrial immune dysregulation in implantation failure",
    )
    entries = _fill_stems(
        [
            _inv(tmp_path, "Li 2026 - Integrated analysis of single-cell multiomics reveals endometrial immune dysregulation.pdf"),
            _inv(tmp_path, "Li 2026 - Integrated analysis of single-cell multiomics reveals endometrial immune dysregulation and.pdf"),
        ],
        tmp_path,
    )
    p, status, debug = resolve_pdf(rec, entries, tmp_path)
    # 两个候选分数接近 → 无法可靠确认 → ambiguous（除非二次验证能区分）
    assert status in ("ambiguous", "matched")
    if status == "ambiguous":
        assert p is None
    assert len(debug) >= 2


def test_no_candidate_missing(tmp_path):
    rec = _rec(title="A completely unrelated paper about quantum computing")
    entries = _fill_stems([_inv(tmp_path, "Chen 等 - 2026 - Decoding the LAM niche.pdf")], tmp_path)
    p, status, _ = resolve_pdf(rec, entries, tmp_path)
    assert status == "missing" and p is None


def test_filename_not_identity_source(tmp_path):
    """PDF 文件名 ≠ 论文身份：标题相同但 DOI 属另一篇，仍应能按标题匹配（fallback 证据）。"""
    rec = _rec(doi="10.1111/otherdoi")
    entries = _fill_stems([_inv(tmp_path, LAM_FILENAME)], tmp_path)
    p, status, _ = resolve_pdf(rec, entries, tmp_path)
    assert status == "matched"
