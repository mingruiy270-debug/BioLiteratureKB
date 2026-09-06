"""Digest prompt 版本管理：项目定制 prompt 的创建 / 激活 / 单篇预览。

约定：prompt 文件 prompts/paper_digest_<version>.md，version 与 config.yaml
digest.version 对应。定制 prompt 从当前激活版本派生，注入 "## 项目聚焦" 段；
激活新版本后 biokb sync 自动按 digest_version 变化全库重读。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .config import Config
from .digest import build_digest
from .models import PaperRecord
from .registry import Registry

FOCUS_MARKER = "## 项目聚焦"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_VERSION_RE = re.compile(r"digest_version:\s*\S+")


def list_prompts(cfg: Config) -> List[dict]:
    out = []
    if cfg.prompts_dir.exists():
        for p in sorted(cfg.prompts_dir.glob("paper_digest_*.md")):
            name = p.stem.removeprefix("paper_digest_")
            text = p.read_text(encoding="utf-8", errors="replace")
            out.append(
                {
                    "name": name,
                    "active": name == cfg.digest_version,
                    "customized": FOCUS_MARKER in text,
                    "size_kb": round(len(text.encode("utf-8")) / 1024, 1),
                }
            )
    return out


def create_prompt(cfg: Config, name: str, from_version: Optional[str] = None) -> Path:
    if not _NAME_RE.match(name):
        raise ValueError(f"非法版本名: {name}（仅允许字母/数字/._-，且以字母数字开头）")
    src_version = from_version or cfg.digest_version
    src = cfg.prompts_dir / f"paper_digest_{src_version}.md"
    if not src.exists():
        raise FileNotFoundError(f"源 prompt 不存在: {src.name}（可用 biokb digest-prompt list 查看）")
    dst = cfg.prompts_dir / f"paper_digest_{name}.md"
    if dst.exists():
        raise FileExistsError(f"版本 {name} 已存在，如需修改请直接编辑 {dst.name}")
    text = src.read_text(encoding="utf-8")
    text = _VERSION_RE.sub(f"digest_version: {name}", text)
    dst.write_text(text, encoding="utf-8")
    return dst


def activate_prompt(cfg: Config, name: str) -> None:
    prompt_file = cfg.prompts_dir / f"paper_digest_{name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"prompt 文件不存在: {prompt_file.name}（可用 biokb digest-prompt create <name> 创建）")
    yaml_file = cfg.root / "config.yaml"
    if not yaml_file.exists():
        raise FileNotFoundError(f"找不到 {yaml_file.name}，无法更新 digest.version")
    lines = yaml_file.read_text(encoding="utf-8").splitlines()
    in_digest = False
    replaced = False
    for i, line in enumerate(lines):
        if re.match(r"^digest\s*:", line):
            in_digest = True
            continue
        if in_digest and re.match(r"^\S", line):  # 离开 digest 段
            break
        if in_digest and re.match(r"^\s*version\s*:", line):
            lines[i] = f'  version: "{name}"'
            replaced = True
            break
    if not replaced:
        raise ValueError("config.yaml 的 digest 段缺少 version 字段，请手动添加：digest.version")
    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def preview_digest(cfg: Config, client, paper: str, version: Optional[str] = None) -> tuple[Path, str]:
    """用指定（默认当前激活）版本的 prompt 重做单篇 digest 到 *.preview.md，不污染正式产物。"""
    use_version = version or cfg.digest_version
    registry = Registry(cfg.registry_file)
    rec = None
    for d in registry.records.values():
        r = PaperRecord(**d)
        if r.paper_id == paper or r.citekey == paper:
            rec = r
            break
    if rec is None:
        raise LookupError(f"未找到论文: {paper}")
    key = rec.citekey or rec.paper_id
    md_path = cfg.md_output_dir / f"{key}.md"
    if not md_path.exists():
        raise FileNotFoundError(f"该论文尚无 Markdown（{md_path.name}），先运行 biokb sync")
    stored = registry.get_record(rec.paper_id)
    if stored and stored.attachment.kb_pdf_path:
        rec.attachment.kb_pdf_path = stored.attachment.kb_pdf_path
        rec.attachment.source_path = stored.attachment.source_path or rec.attachment.source_path
    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    old = cfg.digest_version
    cfg.digest_version = use_version
    try:
        digest_md = build_digest(client, cfg, rec, md_text)
    finally:
        cfg.digest_version = old
    if not digest_md:
        raise RuntimeError("Digest 生成失败（LLM 未配置或调用失败）")
    out = cfg.digest_output_dir / f"{key}.preview.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(digest_md, encoding="utf-8")
    return out
