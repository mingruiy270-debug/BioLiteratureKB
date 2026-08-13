"""Zotero JSON 解析测试。"""
import json

from biokb.zotero import normalize_doi, parse_all, parse_item


def _item(**kw):
    base = {
        "id": 1,
        "type": "article-journal",
        "title": "Single-cell atlas of the human endometrium",
        "citation-key": "garciaSingleCellAtlas",
        "container-title": "Nature",
        "DOI": "10.1038/abc123",
        "author": [{"family": "Garcia", "given": "Ana"}],
        "issued": {"date-parts": [["2024", 1, 1]]},
    }
    base.update(kw)
    return base


def test_doi_normalization():
    assert normalize_doi("10.1038/AbC123") == "10.1038/abc123"
    assert normalize_doi("https://doi.org/10.1038/abc123") == "10.1038/abc123"
    assert normalize_doi("doi:10.1038/abc123") == "10.1038/abc123"
    assert normalize_doi("") == ""
    assert normalize_doi("not a doi") == ""


def test_parse_item_basic():
    rec = parse_item(_item())
    assert rec.paper_id == "10.1038/abc123"  # 无 zotero key → DOI 为 paper_id
    assert rec.citekey == "garciaSingleCellAtlas"
    assert rec.year == 2024
    assert rec.journal == "Nature"
    assert rec.authors == ["Garcia Ana"]


def test_missing_doi_uses_internal_id():
    rec = parse_item(_item(DOI=None))
    assert rec.paper_id.startswith("10.") is False
    assert len(rec.paper_id) == 12  # internal hash


def test_missing_citekey():
    rec = parse_item(_item(**{"citation-key": None}))
    assert rec.citekey == ""
    assert rec.paper_id  # 仍应有 id


def test_zotero_native_format_with_key_and_attachment():
    item = {
        "key": "ABCD1234",
        "title": "Endometrial receptivity in RIF",
        "DOI": "10.1016/j.x.2024.1",
        "date": "2024-05-01",
        "publicationTitle": "Hum Reprod",
        "creators": [{"lastName": "Li", "firstName": "Wei"}],
        "attachments": [
            {"key": "XYZ789", "filename": "Li_2024.pdf", "path": "C:/zotero/storage/XYZ789/Li_2024.pdf", "mimeType": "application/pdf"},
            {"mimeType": "text/plain", "filename": "notes.txt"},
        ],
    }
    rec = parse_item(item)
    assert rec.paper_id == "ABCD1234"
    assert rec.attachment.zotero_attachment_key == "XYZ789"
    assert rec.attachment.original_filename == "Li_2024.pdf"
    assert rec.attachment.source_path == "C:/zotero/storage/XYZ789/Li_2024.pdf"


def test_list_json_and_items_json(tmp_path):
    f1 = tmp_path / "a.json"
    f1.write_text(json.dumps([_item(), _item(id=2, title="Second paper", DOI="10.1038/bbbb123", **{"citation-key": "secondPaper"})]), encoding="utf-8")
    f2 = tmp_path / "b.json"
    f2.write_text(json.dumps({"items": [_item(id=3, title="Third paper", DOI="10.1038/cccc123", **{"citation-key": "thirdPaper"})]}), encoding="utf-8")
    records, dup = parse_all(tmp_path)
    assert len(records) == 3
    assert dup == 0


def test_duplicate_doi_dedup(tmp_path):
    f = tmp_path / "a.json"
    f.write_text(
        json.dumps([_item(), _item(id=2, title="Same DOI different title", DOI="10.1038/ABC123")]),
        encoding="utf-8",
    )
    records, dup = parse_all(tmp_path)
    assert len(records) == 1
    assert dup == 1
