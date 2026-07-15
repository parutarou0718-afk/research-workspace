# 科研工作台 / Research Workspace

本工程包用于启动一个本地优先、可扩展为多 Agent 协同的桌面端科研工作台。

## 产品核心

第一版只验证一个不可由 Excel 替代的核心价值：

> 用户离开一篇论文一段时间后，系统能够基于论文版本、Idea、笔记、会议材料和投稿信息，在几分钟内恢复其研究上下文。

## 建议技术栈

- 桌面端：Python 3.12 + PySide6
- 数据库：SQLite（建议 SQLModel 或 SQLAlchemy 2）
- 文档解析：python-docx、PyMuPDF、python-pptx
- 版本比较：difflib + 段落哈希；后续可替换语义 diff
- 搜索：SQLite FTS5 + 可插拔向量检索
- AI：统一 LLMProvider 接口，首版可接 Gemini/OpenAI/Ollama 任一实现
- 调度：本地 Task 表 + Worker；后续替换为多 Agent Orchestrator
- 事件：SQLite event_log；后续可替换 Redis/NATS/Kafka

## 首发范围

1. 总览
2. 论文项目与版本
3. Idea 库
4. 上下文恢复
5. 投稿总览
6. 手动整理与定期整理

会议、基金、邮箱自动识别、OCR、云同步、多 Agent 均作为扩展模块；但底层契约已经预留。

## 文件说明

- `docs/PRD.docx`：正式产品需求文档
- `docs/PRD.md`：便于 Codex 读取的 PRD
- `docs/ARCHITECTURE.md`：工程架构与模块边界
- `docs/CODEX_INSTRUCTIONS.md`：可直接交给 Codex 的实施指令
- `docs/UI_SPEC.md`：UI 设计规范与页面说明
- `ui/research_workspace_main.ui`：Qt Designer 可打开的主界面原型
- `ui/design_tokens.json`：设计令牌
- `contracts/domain_model.json`：领域对象与关系定义
- `contracts/task_contract.schema.json`：任务协议
- `contracts/event_contract.schema.json`：事件协议
- `contracts/provider_interfaces.md`：可插拔接口规范
- `assets/ui_reference.png`：选定的视觉方向参考图

## 第一条工程原则

原始文件永不被 AI 覆盖。所有 AI 输出均作为候选结果独立保存，带证据来源、模型信息、时间戳和可撤销记录。
