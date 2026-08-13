# BioLiteratureKB — 本地生物医学文献知识库

**Zotero → 本地 PDF → 高质量 Markdown → 深度 Paper Digest → 全文索引 → Progressive Retrieval → Codex / Claude Code Skill**

一个长期可维护的本地科研文献记忆系统。核心目标：让高能力 Agent（Codex / Claude Code）在极低 Context 成本下，按需使用你积累的前沿论文，完成真正的项目特异性科研推理。

```
几百篇论文
  ↓
搜索 10–20 篇        biokb search
  ↓
精读 3–8 篇 Digest    biokb digest
  ↓
深入 1–3 篇原文片段    biokb excerpt
  ↓
Agent 自身完成跨论文比较、方法取舍、科研设计
```

## 定位

- **不是** 生信方案设计器 —— 不替用户选择方法、不做创新评分、不生成 Method Playbook。
- **负责** 同步、保存、解析、深度单篇精读、压缩、索引、精准取回。
- Digest 足够聪明地读懂论文，但**不替未来 Agent 做项目决策**。

## 快速开始（git clone 即用）

### 1. 安装（Windows 双击 `install.bat`；macOS/Linux 运行 `bash install.sh`）

安装脚本自动完成：创建 venv → 安装依赖 → 创建 `.env` → 设置全局 `BIOKB_ROOT`。

也可以手动安装：

```bash
python -m venv .venv
.venv/Scripts/pip install -e .        # Windows；Linux/macOS 用 .venv/bin/pip
```

### 2. 配置 LLM（唯一需要手动的步骤）

编辑 `.env`（从 `.env.example` 复制）：

```text
BIOKB_LLM_API_KEY=你的key
BIOKB_LLM_BASE_URL=https://api.deepseek.com     # 或任何 OpenAI-compatible 服务
BIOKB_LLM_MODEL=deepseek-v4-flash              # 或你的模型名
```

### 3. 放入文献

- 把 Zotero / Better BibTeX 导出的 JSON 放进根目录下任一含 `.json` 的目录（默认自动探测；也可在 `config.yaml` 的 `zotero.json_dir` 显式指定）
- `zotero.storage_root` 默认自动探测常见 Zotero 位置（`D:/zotero/storage`、`~/Zotero/storage` 等）；非标准位置在 `config.yaml` 显式指定

### 4. 首次运行

```bash
biokb doctor      # 环境自检
biokb sync        # 全量同步：PDF 解析 → Markdown → Digest → 索引
biokb status      # 状态总览
```

`biokb sync` 为增量式：JSON 更新时自动重扫 Zotero storage，未变化的论文自动跳过（零 LLM 成本）。

## 常用命令

```bash
biokb doctor                          # 环境自检
biokb sync [--refresh]                # 增量同步（--refresh 强制重扫 storage）
biokb status                          # 状态总览
biokb search "<query>" [--top N]      # 跨库检索候选论文（论文级短结果）
biokb digest <paper_id>               # 深度精读（支持 citekey 别名）
biokb excerpt <paper_id> "<query>"    # 单篇原文精准段落
biokb search-fulltext "<query>"       # 跨库原文段落
```

所有检索命令支持 `--json`（供 Agent 解析）与 `--top`。

## Agent Skill

仓库内置 `skill/bio-literature-kb/SKILL.md`。安装到 Claude Code / Codex 后，Agent 会在科研设计类任务中自动按 `search → digest → excerpt → 原文 → PDF` 的渐进检索顺序调用知识库，绝不批量加载文献。

- Claude Code：复制到 `~/.claude/skills/bio-literature-kb/`
- Codex：复制到项目的 `.codex/skills/` 或用户级 skills 目录

## 目录结构

```
├── zotero来源/                 # 用户数据（git 忽略）
│   ├── json（允许更新）/        # Zotero / Better BibTeX JSON（论文身份来源）
│   ├── 原文PDF/                # 知识库内部 PDF（{citekey}.pdf）
│   └── 原文markdown/           # {citekey}.md（PDF 的忠实文本层）
├── paper_digests/              # {citekey}.md 深度精读（git 忽略）
├── records/                    # {citekey}.json 结构化 Record（git 忽略）
├── index/knowledge_base.sqlite # FTS5 全文索引（git 忽略）
├── system/                     # 状态 / registry / inventory / 日志（git 忽略）
├── prompts/paper_digest_v1.md  # 精读提示词（版本化，可自定义）
├── src/biokb/                  # 核心包
├── skill/bio-literature-kb/    # Agent 行为规则
├── tests/                      # 测试套件
├── config.yaml                 # 配置（auto 自动探测，零配置可用）
├── install.bat / install.sh    # 一键安装
└── .env.example                # LLM 配置模板
```

## 架构要点

- **文献身份来自 Zotero JSON**（citekey / DOI），PDF 文件名只是 fallback 证据
- **PDF 解析四级**：attachment 路径 → attachment key → 文件名精确 → 模糊匹配（含截断标题识别、作者年份前缀剥离、同文不同副本判定）
- **解析器优先级**：docling → mineru → pymupdf4llm（按环境动态检测；MinerU 建议装独立 venv 后在 config 指定 `mineru_bin`）
- **Digest**：单篇单会话深度精读（1M 上下文模型），thinking/effort 可配置；长文自动分段提取后合成
- **索引**：SQLite FTS5（papers / digests / fulltext），无 Vector DB
- **增量**：PDF SHA256 未变 + 产物齐全 → SKIP；JSON 更新 → 自动重扫 storage；digest_version 变化 → 只重做 Digest

## 测试

```bash
.venv/Scripts/python -m pytest tests/ -q
```

覆盖：Zotero JSON 各形态、PDF 解析 8 个 case（含截断标题）、Markdown QC/section、Digest mock LLM、检索全链路、增量同步。

## 已知限制

- Better BibTeX CSL-JSON 不含附件字段，PDF 定位依赖 storage 扫描 + 模糊匹配（Zotero 原生 JSON 含附件时自动走 Level 1–3）
- docling 的版面模型托管在 HuggingFace，网络受限地区可能无法下载（MinerU 模型走 ModelScope 可达）
- FTS5 按词匹配，不支持语义检索；库规模扩大后再引入 embedding
- 需配置 LLM 才能生成 Digest；未配置时 PDF/Markdown/索引全流程照常，Digest 标记 PENDING
