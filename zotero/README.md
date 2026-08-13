# 文献数据目录

把你的 Zotero / Better BibTeX 导出文件放在这里：

- **JSON 文献元数据**：放进 `json/` 子目录（任何含 `.json` 的目录都会被自动探测；也可在 `config.yaml` 中显式指定）
  - Better BibTeX：`Export → Better BibTeX JSON`（不含附件，PDF 自动从 Zotero storage 扫描匹配）
  - 或 Zotero 原生：`File → Export Library → Zotero RDF` 转换 / 第三方工具导出含 attachments 的 JSON
- **PDF 附件**：无需手动放置——`biokb sync` 会自动从你的 Zotero storage 目录（自动探测常见位置）扫描并匹配

运行 `biokb sync` 后，本目录下的 `原文PDF/` 与 `原文markdown/` 会自动生成。
