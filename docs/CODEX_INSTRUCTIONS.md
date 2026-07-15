# 给 Codex 的实施指令

你是本项目的首席桌面应用工程师。请基于本工程包创建一个可运行的 Windows 本地桌面 MVP。

## 必读文件

1. `docs/PRD.md`
2. `docs/ARCHITECTURE.md`
3. `docs/UI_SPEC.md`
4. `contracts/domain_model.json`
5. `contracts/task_contract.schema.json`
6. `contracts/event_contract.schema.json`
7. `contracts/provider_interfaces.md`
8. `ui/research_workspace_main.ui`
9. `assets/ui_reference.png`

## 技术限制

- Python 3.12
- PySide6
- SQLite
- SQLAlchemy 2 或 SQLModel
- pytest
- 不使用浏览器壳或 Electron
- 不强制联网
- 原始文件只读

## 第一阶段交付

创建可运行骨架：

- 主窗口和左侧导航
- 总览、论文、Idea 库、投稿、设置页面
- 会议和基金显示“即将推出”
- SQLite 初始化和迁移
- 示例数据
- 统一日志
- 配置页可选择数据目录

## 第二阶段交付

实现确定性能力：

- 新建论文项目
- 导入 DOCX/PDF/PPTX/TXT/MD
- 文件指纹和增量索引
- 同一项目候选版本识别
- 版本比较摘要
- Idea 新建、状态、来源和多论文关联
- 投稿记录 CRUD 和看板
- 审计日志与撤销

## 第三阶段交付

实现 AI 能力：

- LLMProvider 抽象
- 至少一个 MockProvider，测试不得依赖真实 API
- 可选 Gemini/OpenAI/Ollama Provider
- 手动“立即整理”
- 定时增量整理
- 上下文恢复固定 JSON Schema
- 每条结论关联 EvidenceRef
- AI 结果以候选状态保存

## 架构要求

- UI 不得直接访问数据库或模型 SDK
- 遵守 Presentation/Application/Domain/Infrastructure 分层
- 所有自动任务使用 TaskContract
- 所有重要状态变化写 DomainEvent
- 通过注册表选择 Parser、Provider 和 TaskExecutor
- 不创建真正的多 Agent，但保留 AgentExecutor 适配器

## 数据安全

- 不覆盖或移动用户原始文件
- 解析文本保存为派生数据
- 删除操作默认软删除
- 自动关系可撤销
- 导出 JSON、Markdown 和 CSV
- 提供完整 SQLite 备份

## UI 要求

严格沿用 `assets/ui_reference.png` 的视觉方向：

- 背景 #F6F8FC
- 主色 #4F67F5
- 白色圆角卡片
- 轻阴影
- 蓝紫状态体系
- 中文为主

不要逐像素照抄 AI 图中的乱码和假数据。以 `UI_SPEC.md` 为真实规范。

## 开发顺序

1. 先输出实施计划和目录树。
2. 建立测试和数据库迁移。
3. 完成无 AI 的可运行版本。
4. 再接入 MockProvider 和上下文恢复流水线。
5. 最后接入真实 Provider；没有密钥时应用仍需正常运行。

## 验收测试

必须覆盖：

- 原始文件哈希在全部流程前后不变
- 重复导入被识别
- 一个 Idea 可关联两个论文
- 版本关系可手动纠正
- AI 输出无证据时不得标记为已确认
- 定期扫描只处理新增/变化文件
- Provider 失败不影响手动功能
- 所有自动写入可撤销

## 禁止事项

- 不要把所有业务写进一个 `main.py`
- 不要把 Gemini/OpenAI SDK 写死在 UI 按钮
- 不要直接让 LLM 自由修改数据库
- 不要实现开放式多 Agent 对话
- 不要先开发基金推荐、邮箱自动化或移动端
- 不要牺牲可追溯性来追求“看起来聪明”

完成每个阶段后运行测试，并在 README 中记录启动方式、当前功能和已知限制。
