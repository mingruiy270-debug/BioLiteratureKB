"""digest prompt 版本管理测试：create / list / activate / preview。"""
import re
from pathlib import Path

import pytest

from biokb.config import Config
from biokb.digest_prompt import (
    activate_prompt,
    create_prompt,
    list_prompts,
    preview_digest,
)
from biokb.models import PaperRecord, PaperState
from biokb.registry import Registry


class FakeLLM:
    def __init__(self, cfg):
        self.cfg = cfg
        self.calls = 0

    def chat(self, messages, max_tokens=8000):
        self.calls += 1
        return "# 1. 科研故事\n\n## 1.1 研究背景\nproject-customized digest " * 150


@pytest.fixture
def cfg(tmp_path):
    c = Config(root=tmp_path)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "paper_digest_v1.md").write_text(
        "任务模板 (digest_version: v1)\n# Digest 结构\ndigest_version: v1 输出标记", encoding="utf-8"
    )
    (tmp_path / "config.yaml").write_text(
        "digest:\n  output_dir: \"paper_digests\"\n  version: \"v1\"\n", encoding="utf-8"
    )
    return c


def test_create_replaces_version_markers(cfg):
    dst = create_prompt(cfg, "v2")
    text = dst.read_text(encoding="utf-8")
    assert "digest_version: v2" in text
    assert "digest_version: v1" not in text
    assert dst.name == "paper_digest_v2.md"


def test_create_validation(cfg):
    with pytest.raises(ValueError):
        create_prompt(cfg, "bad name")
    with pytest.raises(FileExistsError):
        create_prompt(cfg, "v1")  # 与源同名 → 已存在


def test_create_missing_source(cfg):
    with pytest.raises(FileNotFoundError):
        create_prompt(cfg, "v2", from_version="nonexistent")


def test_list_marks_active_and_customized(cfg):
    create_prompt(cfg, "v2")
    p = cfg.prompts_dir / "paper_digest_v2.md"
    p.write_text(p.read_text(encoding="utf-8") + "\n## 项目聚焦\n关注 ECM 轴\n", encoding="utf-8")
    items = {it["name"]: it for it in list_prompts(cfg)}
    assert items["v1"]["active"] is True
    assert items["v1"]["customized"] is False
    assert items["v2"]["customized"] is True


def test_activate_updates_config_yaml(cfg):
    create_prompt(cfg, "v2")
    activate_prompt(cfg, "v2")
    c2 = Config(root=cfg.root)
    assert c2.digest_version == "v2"


def test_activate_requires_file(cfg):
    with pytest.raises(FileNotFoundError):
        activate_prompt(cfg, "ghost")


def _make_paper(cfg: Config) -> PaperRecord:
    rec = PaperRecord(
        paper_id="10.1/xyz", citekey="projPaper", title="Custom digest paper",
        year=2026, doi="10.1/xyz", journal="J", authors=["Li Ming"],
    )
    (cfg.md_output_dir).mkdir(parents=True, exist_ok=True)
    (cfg.md_output_dir / "projPaper.md").write_text("# Abstract\n" + "m" * 3000, encoding="utf-8")
    reg = Registry(cfg.registry_file)
    reg.upsert_record(rec)
    st = PaperState(paper_id=rec.paper_id)
    st.status = "digest_ready"
    st.digest_version = "v1"
    reg.set_state(st)
    reg.save()
    return rec


def test_preview_writes_preview_file_only(cfg):
    _make_paper(cfg)
    out = preview_digest(cfg, FakeLLM(cfg), "projPaper", version="v1")
    assert out.name == "projPaper.preview.md" and out.exists()
    assert "project-customized digest" in out.read_text(encoding="utf-8")
    # 正式 digest 未被创建，registry 状态未被改动
    assert not (cfg.digest_output_dir / "projPaper.md").exists()
