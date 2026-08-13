"""PDF → Markdown。按 config parser_priority 顺序尝试，回退到下一 parser。

默认: docling → mineru → pymupdf4llm。
实际环境只装哪个用哪个；命令失败 / 输出为空 / 正文极短 / 明显无效 → fallback。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

MIN_MD_CHARS = 1500


def detect_parsers(mineru_bin: Optional[Path] = None) -> List[str]:
    available: List[str] = []
    try:
        import docling  # noqa: F401

        available.append("docling")
    except ImportError:
        if shutil.which("docling"):
            available.append("docling")
    try:
        import mineru  # noqa: F401

        available.append("mineru")
    except ImportError:
        if (mineru_bin and mineru_bin.exists()) or shutil.which("mineru"):
            available.append("mineru")
    try:
        import pymupdf4llm  # noqa: F401

        available.append("pymupdf4llm")
    except ImportError:
        pass
    return available


def _looks_valid(md: str) -> bool:
    md = md.strip()
    if not md:
        return False
    if len(md) < MIN_MD_CHARS:
        return False
    # 明显乱码 / 二进制垃圾
    printable = sum(1 for c in md[:4000] if c.isprintable() or c in "\n\t")
    if printable / max(1, min(len(md), 4000)) < 0.9:
        return False
    return True


def _docling_convert(pdf: Path, out: Path) -> bool:
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore
        from docling.datamodel.base_models import InputFormat  # type: ignore
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend  # type: ignore

        # 默认 docling-parse (Rust) 在含中文的路径下无法加载资源文件 → 改用 pypdfium2
        conv = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(backend=PyPdfiumDocumentBackend)
            }
        )
        result = conv.convert(str(pdf))
        md = result.document.export_to_markdown()
        if _looks_valid(md):
            out.write_text(md, encoding="utf-8")
            return True
        return False
    except Exception:  # noqa: BLE001
        return False


def _mineru_convert(pdf: Path, out: Path, bin_path: Optional[Path] = None) -> bool:
    try:
        exe: Optional[str] = None
        if bin_path and bin_path.exists():
            exe = str(bin_path)
        elif shutil.which("mineru"):
            exe = shutil.which("mineru")
        else:
            return False
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [exe, "-p", str(pdf), "-o", tmp, "-b", "pipeline"],
                capture_output=True, timeout=900,
            )
            if proc.returncode != 0:
                return False
            md_files = list(Path(tmp).rglob("*.md"))
            if not md_files:
                return False
            md = "".join(f.read_text(encoding="utf-8") for f in md_files)
            if _looks_valid(md):
                out.write_text(md, encoding="utf-8")
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


def _pymupdf4llm_convert(pdf: Path, out: Path) -> bool:
    try:
        import pymupdf4llm  # type: ignore

        md = pymupdf4llm.to_markdown(str(pdf))
        if _looks_valid(md):
            out.write_text(md, encoding="utf-8")
            return True
        return False
    except Exception:  # noqa: BLE001
        return False


_PARSERS = {
    "docling": _docling_convert,
    "pymupdf4llm": _pymupdf4llm_convert,
}


def convert_pdf(pdf: Path, out_md: Path, priority: List[str], mineru_bin: Optional[Path] = None) -> Tuple[str, str]:
    """返回 (status, parser)。status ∈ ok | failed。"""
    out_md.parent.mkdir(parents=True, exist_ok=True)
    for name in priority:
        if name == "mineru":
            ok = _mineru_convert(pdf, out_md, mineru_bin)
        else:
            fn = _PARSERS.get(name)
            if fn is None:
                continue
            try:
                ok = fn(pdf, out_md)
            except Exception:  # noqa: BLE001
                ok = False
        if ok:
            return "ok", name
    return "failed", ""


def add_frontmatter(md_path: Path, fields: dict) -> None:
    """在 Markdown 顶部写入 YAML frontmatter（已有则跳过）。"""
    if not md_path.exists():
        return
    text = md_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        return
    lines = ["---"]
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, str) and "\n" not in v and ":" in v:
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines += ["---", ""]
    md_path.write_text("\n".join(lines) + text, encoding="utf-8")
