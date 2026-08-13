"""配置加载：config.yaml + 环境变量 + 自动探测。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv

USER_ROOT_FILE = Path.home() / ".biokb_root"


def find_project_root() -> Path:
    """知识库根目录解析顺序：BIOKB_ROOT 环境变量 → ~/.biokb_root → 包内启发式。"""
    env = os.environ.get("BIOKB_ROOT")
    if env and Path(env).exists():
        return Path(env)
    if USER_ROOT_FILE.exists():
        try:
            p = Path(USER_ROOT_FILE.read_text(encoding="utf-8").strip().strip('"'))
            if p.exists():
                return p
        except OSError:
            pass
    # pip 安装（site-packages）或源码仓库内的启发式：向上找含 src/biokb/config.py 的根
    here = Path(__file__).resolve()
    for candidate in [here.parents[2], Path.cwd()]:
        if (candidate / "config.yaml").exists():
            return candidate
    return here.parents[2]


def detect_zotero_storage(explicit: Optional[Path]) -> Path:
    """显式配置优先；否则探测常见 Zotero storage 位置。"""
    if explicit is not None:
        return explicit
    candidates = [
        Path("D:/zotero/storage"),
        Path.home() / "Zotero" / "storage",
        Path.home() / "Documents" / "Zotero" / "storage",
        Path.home() / "OneDrive" / "Zotero" / "storage",
    ]
    for c in candidates:
        if c.exists() and next(c.rglob("*.pdf"), None) is not None:
            return c
    return candidates[0]  # 都没找到时用最常见位置（doctor 会提示 MISSING）


_INTERNAL_DIRS = {"records", "system", "paper_digests", "index", "prompts", "tests", "skill", "src"}


def detect_json_dir(root: Path, explicit: Optional[Path]) -> Path:
    """显式配置优先；否则在根目录下找含 *.json 的实际目录（含子目录，排除系统内部目录）。"""
    if explicit is not None:
        return explicit
    if root.exists():
        hits: List[Path] = []
        for d in root.iterdir():
            if not d.is_dir() or d.name in _INTERNAL_DIRS:
                continue
            if next(d.rglob("*.json"), None) is not None:
                hits.append(d)
        if hits:
            # 目录名含 zotero 或 json 的优先
            for d in hits:
                if "zotero" in d.name.lower() or "json" in d.name.lower():
                    # 若 JSON 在其子目录（如 zotero来源/json/），返回实际含 JSON 的子目录
                    direct = next(d.glob("*.json"), None)
                    if direct is not None:
                        return d
                    subs = [sd for sd in d.iterdir() if sd.is_dir() and next(sd.rglob("*.json"), None) is not None]
                    if subs:
                        prefer = [sd for sd in subs if "json" in sd.name.lower()] or subs
                        return prefer[0]
                    return d
            return max(hits, key=lambda d: len(list(d.rglob("*.json"))))
    return root / "zotero" / "json"


class Config:
    def __init__(self, root: Path | None = None):
        load_dotenv()
        self.root: Path = (root or find_project_root()).resolve()
        raw = self._load_yaml(self.root / "config.yaml")

        zotero = raw.get("zotero", {})
        json_val = str(zotero.get("json_dir", "") or "").strip()
        storage_val = str(zotero.get("storage_root", "") or "").strip()
        self.zotero_json_dir = detect_json_dir(
            self.root,
            self._p(zotero, "json_dir", "zotero/json") if json_val and json_val.lower() != "auto" else None,
        )
        self.zotero_storage_root = detect_zotero_storage(
            self._p(zotero, "storage_root", "") if storage_val and storage_val.lower() != "auto" else None
        )

        self.pdf_output_dir = self._p(raw, "pdf", "output_dir", "zotero/原文PDF")
        self.pdf_inventory_file = self._p(raw, "pdf", "inventory_file", "system/pdf_inventory.json")
        self.md_output_dir = self._p(raw, "markdown", "output_dir", "zotero/原文markdown")
        self.parser_priority: List[str] = raw.get("markdown", {}).get(
            "parser_priority", ["docling", "mineru", "pymupdf4llm"]
        )
        mineru_bin = raw.get("markdown", {}).get("mineru_bin", "")
        self.mineru_bin: Optional[Path] = None
        if mineru_bin:
            p = Path(mineru_bin)
            self.mineru_bin = p if p.is_absolute() else self.root / p
        self.digest_output_dir = self._p(raw, "digest", "output_dir", "paper_digests")
        self.record_dir = self._p(raw, "digest", "record_dir", "records")
        self.digest_version = raw.get("digest", {}).get("version", "v1")
        self.max_chars_per_call = int(
            raw.get("digest", {}).get("max_chars_per_call", 400000)
        )
        llm = raw.get("llm", {})
        self.llm_base_url_env = llm.get("base_url_env", "BIOKB_LLM_BASE_URL")
        self.llm_api_key_env = llm.get("api_key_env", "BIOKB_LLM_API_KEY")
        self.llm_model_env = llm.get("model_env", "BIOKB_LLM_MODEL")
        self.llm_temperature = float(llm.get("temperature", 0.0))
        self.llm_timeout_seconds = int(llm.get("timeout_seconds", 600))
        self.llm_max_retries = int(llm.get("max_retries", 3))
        self.llm_max_tokens = int(llm.get("max_tokens", 384000))
        self.llm_thinking = os.environ.get("BIOKB_LLM_THINKING", llm.get("thinking", "enabled"))
        self.llm_reasoning_effort = os.environ.get("BIOKB_LLM_REASONING_EFFORT", llm.get("reasoning_effort", "max"))
        retr = raw.get("retrieval", {})
        self.default_search_top = int(retr.get("default_search_top", 10))
        self.default_excerpt_top = int(retr.get("default_excerpt_top", 5))
        self.default_max_chars = int(retr.get("default_max_chars", 12000))
        self.continue_on_error = bool(raw.get("runtime", {}).get("continue_on_error", True))

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        return data

    def _p(self, raw: dict, section: str, key: str, default: str = "") -> Optional[Path]:
        val = (raw.get(section, {}).get(key) or "") or default
        if not val:
            return None
        p = Path(str(val))
        return p if p.is_absolute() else self.root / p

    # ---- 目录快捷属性 ----
    @property
    def index_db(self) -> Path:
        return self.root / "index" / "knowledge_base.sqlite"

    @property
    def system_dir(self) -> Path:
        return self.root / "system"

    @property
    def state_file(self) -> Path:
        return self.system_dir / "state.json"

    @property
    def registry_file(self) -> Path:
        return self.system_dir / "paper_registry.json"

    @property
    def failed_file(self) -> Path:
        return self.system_dir / "failed.json"

    @property
    def build_log_file(self) -> Path:
        return self.system_dir / "build.log"

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"

    def ensure_dirs(self) -> None:
        for d in [
            self.zotero_json_dir,
            self.pdf_output_dir,
            self.md_output_dir,
            self.digest_output_dir,
            self.record_dir,
            self.index_db.parent,
            self.system_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # ---- LLM 环境 ----
    def llm_env_status(self) -> dict:
        """只暴露是否已设置，不暴露真实值。"""
        key = os.environ.get(self.llm_api_key_env, "")
        key_status = "MISSING"
        if key:
            # 占位符（含非 ASCII 或常见示例文本）视为未真正配置
            key_status = "PLACEHOLDER" if (not key.isascii() or "xxxx" in key or "你的" in key) else "SET"
        return {
            "api_key": key_status,
            "base_url": "SET" if os.environ.get(self.llm_base_url_env) else "MISSING",
            "model": "SET" if os.environ.get(self.llm_model_env) else "MISSING",
        }

    def llm_configured(self) -> bool:
        return all(
            os.environ.get(self.llm_api_key_env),
            os.environ.get(self.llm_base_url_env),
            os.environ.get(self.llm_model_env),
        )


def get_config(root: Path | None = None) -> Config:
    return Config(root)
