# BioLiteratureKB — 本地科研文献知识库

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)

**Zotero → 本地 PDF → 高质量 Markdown → 深度 Paper Digest → 全文索引 → Progressive Retrieval → Codex / Claude Code Skill**

一个长期可维护的本地科研文献记忆系统。核心目标：让高能力 Agent（Codex / Claude Code）在极低 Context 成本下，按需使用你积累的前沿论文，完成科研全流程（选题 → 设计 → 分析 → 干湿整合 → 写作 → 修改/审稿 → 汇报）的项目特异性工作。

```
几百篇论文
  ↓
搜索候选论文          biokb search
  ↓
精读相关 Digest        biokb digest
  ↓
深入原文片段          biokb excerpt
  ↓
Agent 自行完成跨论文比较、方法取舍、设计决策、稿件撰写
```

检索与精读的数量**由 Agent 按任务需要自行决定**（`--top N` 可调），不受固定上限约束。

## 定位

- **覆盖科研全流程**：选题、研究设计、数据分析（生信/多组学/ML/单细胞/空间/扰动）、干湿整合、论文写作、修改/审稿、汇报——任何科研相关任务都可调用。
- **负责** 同步、保存、解析、深度单篇精读、压缩、索引、精准取回。
- **不替 Agent 做决策**：Digest 足够聪明地读懂论文，但方法取舍、创新判断、设计决策、稿件撰写等推理责任始终在运行时 Agent。
- **不限制领域**：生物医学开箱即用；通过项目定制精读提示词可扩展到**任何领域**（深度学习、机器学习、CV/NLP、材料、社科等）。跨领域、跨主题的前沿论文都是方法学与写作模式的学习来源。

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
biokb sync --concurrency 12           # 指定 digest 并发数（覆盖配置）
biokb status                          # 状态总览
biokb search "<query>" [--top N]      # 跨库检索候选论文（论文级短结果）
biokb digest <paper_id>               # 深度精读（支持 citekey 别名）
biokb excerpt <paper_id> "<query>"    # 单篇原文精准段落
biokb search-fulltext "<query>"       # 跨库原文段落
biokb digest-prompt list              # digest prompt 版本列表
biokb digest-prompt test <paper>      # 用某版本 prompt 单篇试跑（.preview.md）
```

所有检索命令支持 `--json`（供 Agent 解析）与 `--top`。

## 并发加速

Digest 的 LLM 调用是主要耗时项（每篇约 5–7 分钟）。同步时**多篇并行精读**，大幅缩短全量重读时间：

```bash
biokb sync --concurrency 12           # 命令行覆盖
BIOKB_CONCURRENCY=12 biokb sync       # 环境变量覆盖
```

```yaml
# config.yaml
digest:
  concurrency: 10     # 默认 10；官方并发上限 20
```

- **并行范围**：只并行纯 LLM 调用；PDF 解析、状态写入、索引建库仍在主线程串行，保证数据一致
- **提速参考**：10 篇 × 6 分钟，串行约 60 分钟 → 并发 10 约 6–10 分钟
- **注意**：并发过高可能触发 API 速率限制（429），失败篇目会记录到 `system/failed.json`，下次 sync 自动重试
- **进度**：`system/build.log` 中 `digest | PROGRESS | i/N` 实时显示完成数

## 项目定制 Digest Prompt（领域无关的关键机制）

每篇论文的 Digest 由版本化的精读提示词（`prompts/paper_digest_<version>.md`）驱动。**Digest 管线本身不绑定任何领域**——默认提示词面向生物医学，但精读提示词完全可以个性化定制：你提供项目文档（研究设计、分析总结、领域术语表、关注的方法体系），生成的定制提示词让每一篇精读都按你项目的核心问题与关注维度进行有重点的提取。

因此，通过一次定制即可把整个知识库适配到**任何领域**：

- **生物医学**（默认）：功能轴、细胞类型、湿实验、干湿证据链…
- **深度学习 / 机器学习**：模型架构、数据集与基准、训练策略、消融实验、评估指标、复现细节…
- **其他科研领域**（CV/NLP、材料、化学、社科…）：任意领域术语与论文结构均可写入「项目聚焦」段

```bash
biokb digest-prompt create my-project   # 从当前版本派生定制版（注入「## 项目聚焦」段）
biokb digest-prompt test <paper_id> --version my-project   # 单篇试跑验收
biokb digest-prompt use my-project      # 激活 → biokb sync 全库按新提示词重读
```

- **Agent 可自主执行全流程**：把项目文档路径交给 Claude Code / Codex（配合仓库内置 skill），Agent 会自动完成——阅读项目文档 → 起草并注入定制提示词 → 单篇试跑 → 展示给你验收 → 批准后激活并全库重读。你只需提供文档并做最终验收。
- **何时启用**：仅首次设置 skill 且你提供项目文档时，或你明确要求修改时（一次性设置，非日常流程）
- **可定制**：提取详略、关注维度、术语偏好
- **不可放宽**：事实纪律（`not_reported`/`unclear`/`null`、不编造、预测≠因果、Digest 内不做项目建议）

## Agent Skill

仓库内置 `skill/bio-literature-kb/SKILL.md`。安装到 Claude Code / Codex 后，Agent 会在科研全流程任务（选题、设计、分析、干湿整合、写作、修改/审稿、汇报）中自动按 `search → digest → excerpt → 原文 → PDF` 的渐进检索顺序调用知识库，从不同疾病与主题的前沿论文中学习方法学与写作模式，绝不批量加载文献。

**Claude Code**（Windows PowerShell）：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills\bio-literature-kb"
Copy-Item "skill\bio-literature-kb\SKILL.md" "$env:USERPROFILE\.claude\skills\bio-literature-kb\"
```

**Codex**：复制到项目的 `.codex/skills/` 或用户级 skills 目录。

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
├── prompts/paper_digest_v1.md  # 精读提示词（版本化；digest-prompt 派生定制版）
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
- **Digest**：单篇单会话深度精读（1M 上下文模型），thinking/effort 可配置；长文自动分段提取后合成；多篇 LLM 调用并发执行（`digest.concurrency`）
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
