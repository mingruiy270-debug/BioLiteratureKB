"""配置自动探测测试。"""
import json
from pathlib import Path

from biokb.config import Config, detect_json_dir, detect_zotero_storage


def test_detect_json_dir_explicit(tmp_path):
    explicit = tmp_path / "myjsons"
    explicit.mkdir()
    assert detect_json_dir(tmp_path, explicit) == explicit


def test_detect_json_dir_prefers_zotero_named(tmp_path):
    # 中文目录名 + JSON 在子目录里（真实场景：zotero来源/json（允许更新）/）
    src = tmp_path / "zotero来源" / "json（允许更新）"
    src.mkdir(parents=True)
    (src / "papers.json").write_text("[]", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    (other / "x.json").write_text("[]", encoding="utf-8")
    found = detect_json_dir(tmp_path, None)
    assert found == src


def test_detect_json_dir_excludes_internal(tmp_path):
    # records/ 是系统输出目录，不应被探测为 JSON 来源
    (tmp_path / "records").mkdir()
    (tmp_path / "records" / "r.json").write_text("{}", encoding="utf-8")
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "s.json").write_text("{}", encoding="utf-8")
    found = detect_json_dir(tmp_path, None)
    assert found != tmp_path / "records"
    assert found != tmp_path / "system"
    # 无外部 JSON → 回退默认目录
    assert found == tmp_path / "zotero" / "json"


def test_detect_storage_explicit(tmp_path):
    explicit = tmp_path / "storage"
    explicit.mkdir()
    assert detect_zotero_storage(explicit) == explicit


def test_config_auto_resolution(tmp_path):
    # 干净环境：无 config.yaml 也能构建 Config，目录全部解析到根下
    cfg = Config(root=tmp_path)
    assert cfg.root == tmp_path.resolve()
    assert cfg.index_db.parent == tmp_path / "index"
    assert cfg.digest_version == "v1"
    assert cfg.llm_max_tokens == 384000
    cfg.ensure_dirs()
    assert (tmp_path / "paper_digests").exists()
    assert (tmp_path / "index").exists()
