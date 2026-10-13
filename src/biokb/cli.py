"""biokb CLI：doctor / status / sync / search / digest / excerpt / search-fulltext。"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Windows 中文控制台默认 GBK，强制 UTF-8 输出，保证 --json 管道与 Agent 读取正确
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich.console import Console
from rich.table import Table

from .config import Config, get_config
from .converter import detect_parsers
from .digest_prompt import activate_prompt, create_prompt, list_prompts, preview_digest
from .indexer import Indexer
from .llm_client import LLMClient
from .pdf_inventory import load_inventory
from .registry import Registry
from .retrieval import NotFound, Retrieval
from .state import load_failed, load_state
from .sync import run_sync
from .zotero import parse_all

app = typer.Typer(add_completion=False, help="BioLiteratureKB — 本地生物医学文献知识库")
app_group = typer.Typer(help="Digest prompt 版本管理（项目定制）", no_args_is_help=True)
app.add_typer(app_group, name="digest-prompt")
console = Console()


@app.command("review-pdf")
def review_pdf(
    pdf: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", help="Dedicated single-paper output directory"),
    version: str = typer.Option("research_deepread_v2", "--version"),
    pages: str = typer.Option("none", "--pages", help="Default text-only; auto previews candidates; explicit pages: 5,6"),
    formula_crops: Optional[Path] = typer.Option(None, "--formula-crops", exists=True, dir_okay=False,
        help="JSON list of explicit {page,bbox,reason} equation crops; normalized bbox; incompatible with --pages"),
    max_vision_pages: int = typer.Option(2, "--max-vision-pages"),
    max_calls: int = typer.Option(5, "--max-calls"),
    max_reserved_tokens: int = typer.Option(800000, "--max-reserved-tokens"),
    max_usd: float = typer.Option(0.0, "--max-usd", help="Optional whole-run estimated money cap; 0 = no cap on text spending"),
    max_vision_usd: float = typer.Option(.02, "--max-vision-usd", help="Separate visual-attempt budget, USD"),
    digest_max_tokens: int = typer.Option(393216, "--digest-max-tokens", help="Report output ceiling, not a target length"),
    input_rate: float = typer.Option(.30, "--input-rate", help="USD per million input tokens; verify provider rates"),
    output_rate: float = typer.Option(1.20, "--output-rate", help="USD per million output tokens"),
    apply: bool = typer.Option(False, "--apply", help="Explicitly permit bounded API calls"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """One PDF: native text + selected visual pages + generic digest. Default: no API."""
    from .paper_review import Limits, ReviewError, run_review
    try:
        result = run_review(Config(Path(root) if root else None, discover_sources=False), pdf, output, version, pages,
                            Limits(max_vision_pages=max_vision_pages, max_calls=max_calls,
                                   max_reserved_tokens=max_reserved_tokens, max_usd=max_usd, max_vision_usd=max_vision_usd, digest_output_tokens=digest_max_tokens,
                                   input_usd_per_million=input_rate, output_usd_per_million=output_rate), apply,
                            formula_crops=json.loads(formula_crops.read_text(encoding="utf-8")) if formula_crops else None)
    except (ReviewError, ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print_json(data={"status": result["status"], "output": str(output),
                             "plan": result["plan"], "actual_usage": result.get("actual_usage"),
                             "semantic_review_status": result.get("semantic_review_status"),
                             "review_warnings": result.get("review_warnings", [])})


@app.command("complete-review")
def complete_review(
    output: Path = typer.Argument(..., exists=True, file_okay=False),
    apply: bool = typer.Option(False, "--apply", help="Explicitly permit one additional final text call within existing cost ceiling"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """Complete a known truncated final digest; preserve earlier usage, no image calls."""
    from .paper_review import complete_text_preview, ReviewError
    try:
        result = complete_text_preview(Config(Path(root) if root else None, discover_sources=False), output, apply)
    except (ReviewError, ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print_json(data=result)


def _cfg(root: Optional[str]) -> Config:
    if root:
        return get_config(Path(root))
    return get_config(None)


@app.command("doctor")
def doctor(root: Optional[str] = typer.Option(None, "--root", help="知识库根目录")):
    """环境自检。"""
    cfg = _cfg(root)
    checks = []
    checks.append(("Python", f"{sys.version.split()[0]}"))
    try:
        import sqlite3 as s
        fts_ok = s.connect(":memory:").execute("select sqlite_compileoption_used('ENABLE_FTS5')").fetchone()[0]
        checks.append(("SQLite/FTS5", f"{s.sqlite_version} / {'OK' if fts_ok else 'NO'}"))
    except Exception as e:  # noqa: BLE001
        checks.append(("SQLite/FTS5", f"ERROR {e}"))
    checks.append(("KB root", str(cfg.root)))
    json_count = len(list(cfg.zotero_json_dir.glob("*.json"))) if cfg.zotero_json_dir.exists() else 0
    checks.append(("Zotero JSON", f"{json_count} file(s)" if json_count else "MISSING"))
    checks.append(("Zotero storage", "OK" if cfg.zotero_storage_root.exists() else "MISSING"))
    try:
        test = cfg.system_dir
        test.mkdir(parents=True, exist_ok=True)
        (test / ".write_test").write_text("x")
        (test / ".write_test").unlink()
        checks.append(("Write permission", "OK"))
    except Exception as e:  # noqa: BLE001
        checks.append(("Write permission", f"FAIL {e}"))
    parsers = detect_parsers(cfg.mineru_bin)
    for p in ("docling", "mineru", "pymupdf4llm"):
        checks.append((f"Parser: {p}", "OK" if p in parsers else "not installed"))
    env = cfg.llm_env_status()
    checks.append(("LLM API key", env["api_key"]))
    checks.append(("LLM base URL", env["base_url"]))
    checks.append(("LLM model", env["model"]))
    tbl = Table(title="biokb doctor")
    tbl.add_column("Item")
    tbl.add_column("Status")
    for name, status in checks:
        color = "green" if "OK" in status or "SET" in status else "yellow" if "not installed" in status else "red"
        tbl.add_row(name, f"[{color}]{status}[/{color}]")
    console.print(tbl)


@app.command("status")
def status(root: Optional[str] = typer.Option(None, "--root")):
    """知识库状态总览。"""
    cfg = _cfg(root)
    records, dup = parse_all(cfg.zotero_json_dir)
    registry = Registry(cfg.registry_file)
    states = registry.states
    inv = load_inventory(cfg.pdf_inventory_file)
    md_files = list(cfg.md_output_dir.glob("*.md")) if cfg.md_output_dir.exists() else []
    dg_files = list(cfg.digest_output_dir.glob("*.md")) if cfg.digest_output_dir.exists() else []
    fail = load_failed(cfg.failed_file)
    try:
        idx = Indexer(cfg.index_db)
        stats = idx.stats()
        idx.close()
    except Exception:  # noqa: BLE001
        stats = {}
    pdf_status = {}
    for s in states.values():
        st = s.get("status", "new")
        pdf_status[st] = pdf_status.get(st, 0) + 1
    resolved_any = sum(pdf_status.get(k, 0) for k in ("pdf_ready", "md_ready", "digest_ready", "failed"))
    tbl = Table(title="biokb status")
    tbl.add_column("Item")
    tbl.add_column("Count")
    rows = [
        ("Zotero items (JSON)", len(records) + dup),
        ("Unique papers", len(records)),
        ("Duplicates", dup),
        ("Zotero storage PDFs (inventory)", len(inv)),
        ("PDF resolved (any)", resolved_any),
        ("  missing", pdf_status.get("missing", 0)),
        ("  ambiguous", pdf_status.get("ambiguous", 0)),
        ("Markdown ready", len(md_files)),
        ("Digest ready", len(dg_files)),
        ("Digest pending", sum(1 for s in states.values() if s.get("status") == "md_ready")),
        ("Indexed papers", stats.get("papers", 0)),
        ("Indexed sections", stats.get("fulltext_sections", 0)),
        ("Failed (failed.json)", len(fail)),
    ]
    for name, cnt in rows:
        tbl.add_row(name, str(cnt))
    console.print(tbl)
    state = load_state(cfg.state_file)
    if state.get("last_sync"):
        console.print(f"[dim]last sync: {state['last_sync']}[/dim]")


@app_group.command("list")
def dp_list(root: Optional[str] = typer.Option(None, "--root")):
    """列出所有 digest prompt 版本。"""
    cfg = _cfg(root)
    items = list_prompts(cfg)
    tbl = Table(title=f"digest prompts (active: {cfg.digest_version})")
    tbl.add_column("version")
    tbl.add_column("active")
    tbl.add_column("customized")
    tbl.add_column("size(KB)")
    for it in items:
        flag = "✓" if it["active"] else ""
        tbl.add_row(it["name"], flag, "✓" if it["customized"] else "", str(it["size_kb"]))
    console.print(tbl)


@app_group.command("create")
def dp_create(
    name: str,
    from_version: Optional[str] = typer.Option(None, "--from", help="源版本（默认当前激活版本）"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """从当前版本派生新的定制 prompt。"""
    cfg = _cfg(root)
    try:
        dst = create_prompt(cfg, name, from_version)
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]已创建: {dst}[/green]")
    console.print("编辑通用精读规则；只有用户明确要求项目聚焦时才加入项目背景，避免限制单篇知识提取。")
    console.print("定制只影响详略与聚焦，不得放宽事实纪律（not_reported / 不编造 / 不写项目建议）。")
    console.print("完成后: biokb digest-prompt test <paper_id> --version <name>   # 单篇试跑")


@app_group.command("use")
def dp_use(
    name: str,
    root: Optional[str] = typer.Option(None, "--root"),
):
    """激活指定版本为当前 digest prompt（运行 sync 后全库按新版本重读）。"""
    cfg = _cfg(root)
    try:
        activate_prompt(cfg, name)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]digest.version = {name}[/green]")
    console.print("下次运行 biokb sync 将按 digest_version 变化重做全部 Digest（每篇约 5-7 分钟）。")
    console.print("建议先 biokb digest-prompt test <paper_id> --version <name> 试跑一篇确认质量。")


@app_group.command("test")
def dp_test(
    paper: str,
    version: Optional[str] = typer.Option(None, "--version", help="试跑的 prompt 版本（默认当前激活版本）"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """用指定 prompt 版本单篇重做 digest 预览（写入 *.preview.md，不污染正式产物）。"""
    cfg = _cfg(root)
    if not cfg.llm_configured():
        console.print("[red]LLM 未配置，无法生成 Digest[/red]")
        raise typer.Exit(1)
    client = LLMClient(cfg)
    try:
        out = preview_digest(cfg, client, paper, version)
    except (LookupError, FileNotFoundError, RuntimeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    size = out.stat().st_size
    console.print(f"[green]预览已写入: {out} ({size/1024:.1f} KB)[/green]")
    console.print("检查质量后：满意 → biokb digest-prompt use <version>；不满意 → 直接编辑 prompt 后重跑本命令。")


@app.command("sync")
def sync(
    refresh: bool = typer.Option(False, "--refresh", help="强制重新扫描 Zotero storage"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="digest 并发数（默认取 config.yaml digest.concurrency）"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """全量同步：JSON → PDF → Markdown → Digest → Index。"""
    cfg = _cfg(root)
    if concurrency is not None:
        cfg.concurrency = max(1, int(concurrency))
    with console.status(f"[bold green]syncing... (digest 并发 {cfg.concurrency})"):
        report = run_sync(cfg, refresh_inventory=refresh)
    tbl = Table(title="sync report")
    tbl.add_column("Stage")
    tbl.add_column("Count")
    rows = [
        ("Zotero items", report.zotero_items),
        ("Unique papers", report.unique_papers),
        ("Duplicates", report.duplicates),
        ("PDF matched", report.pdf_status.get("matched", 0)),
        ("PDF ambiguous", report.pdf_status.get("ambiguous", 0)),
        ("PDF missing", report.pdf_status.get("missing", 0)),
        ("Markdown ok", report.markdown.get("ok", 0)),
        ("Markdown skipped", report.markdown.get("skipped", 0)),
        ("Markdown failed", report.markdown.get("failed", 0)),
        ("Digest ready", report.digest.get("ready", 0)),
        ("Digest pending", report.digest.get("pending", 0)),
        ("Digest failed", report.digest.get("failed", 0)),
        ("Digest skipped", report.digest.get("skipped", 0)),
        ("Indexed sections", report.indexed),
        ("Pipeline errors", len(report.failed)),
    ]
    for name, cnt in rows:
        tbl.add_row(name, str(cnt))
    console.print(tbl)
    if report.failed:
        console.print("[red]errors — 详见 system/failed.json 与 system/build.log[/red]")


def _search_table(results, title: str) -> None:
    tbl = Table(title=title)
    for col in ("paper_id", "citekey", "year", "title", "score", "data_types", "methods"):
        tbl.add_column(col, max_width=42)
    for r in results:
        tbl.add_row(
            r.get("paper_id", ""), r.get("citekey", ""), str(r.get("year", "")),
            (r.get("title") or "")[:80], str(r.get("score", "")),
            (r.get("data_types") or "")[:40], (r.get("methods") or "")[:40],
        )
    console.print(tbl)


@app.command("search")
def search(
    query: str,
    top: int = typer.Option(None, "--top"),
    as_json: bool = typer.Option(False, "--json"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """跨库检索候选论文（只返回论文级短结果）。"""
    cfg = _cfg(root)
    results = Retrieval(cfg).search(query, top)
    if as_json:
        sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=1) + "\n")
        return
    if not results:
        console.print("无结果。可尝试更短的关键词。")
        return
    _search_table(results, f'search: "{query}"')


@app.command("digest")
def digest(
    paper: str,
    as_json: bool = typer.Option(False, "--json"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """读取某篇论文的 Paper Digest（paper_id 或 citekey）。"""
    cfg = _cfg(root)
    try:
        d = Retrieval(cfg).digest(paper)
    except NotFound as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if as_json:
        sys.stdout.write(json.dumps({"paper_id": d["paper_id"], "title": d.get("title", ""), "digest": d["digest"]}, ensure_ascii=False, indent=1) + "\n")
        return
    console.print(f"[bold]{d.get('title', d['paper_id'])}[/bold]  [dim]{d.get('year', '')} · {d.get('journal', '')}[/dim]")
    console.print(d["digest"])


@app.command("excerpt")
def excerpt(
    paper: str,
    query: str,
    top: int = typer.Option(None, "--top"),
    max_chars: int = typer.Option(None, "--max-chars"),
    as_json: bool = typer.Option(False, "--json"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """在某篇论文原文中精准检索段落。"""
    cfg = _cfg(root)
    try:
        results = Retrieval(cfg).excerpt(paper, query, top, max_chars)
    except NotFound as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if as_json:
        sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=1) + "\n")
        return
    if not results:
        console.print("无匹配段落。")
        return
    tbl = Table(title=f'excerpt: "{query}" @ {paper}')
    tbl.add_column("paper")
    tbl.add_column("section")
    tbl.add_column("rank")
    tbl.add_column("snippet")
    for r in results:
        tbl.add_row(paper, r["section"], str(r["rank"]), r["snippet"][:600])
    console.print(tbl)


@app.command("search-fulltext")
def search_fulltext(
    query: str,
    top: int = typer.Option(None, "--top"),
    max_chars: int = typer.Option(None, "--max-chars"),
    as_json: bool = typer.Option(False, "--json"),
    root: Optional[str] = typer.Option(None, "--root"),
):
    """跨整个知识库搜索原文段落。"""
    cfg = _cfg(root)
    results = Retrieval(cfg).search_fulltext(query, top, max_chars)
    if as_json:
        sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=1) + "\n")
        return
    if not results:
        console.print("无匹配段落。")
        return
    tbl = Table(title=f'search-fulltext: "{query}"')
    tbl.add_column("paper_id")
    tbl.add_column("section")
    tbl.add_column("snippet")
    for r in results:
        tbl.add_row(r["paper_id"], r["section"], r["snippet"][:600])
    console.print(tbl)


def main() -> None:
    app()
