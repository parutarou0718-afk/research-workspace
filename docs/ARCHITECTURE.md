# 工程架构说明 v0.1

## 1. 架构目标

- Local-first
- Agent-ready，而非首版强行多 Agent
- 所有核心能力通过统一契约调用
- 保留模块替换能力，不做过度插件化
- 原始文档不可变、AI 输出可追溯

## 2. 推荐目录结构

```text
research_workspace/
├─ app.py
├─ pyproject.toml
├─ src/
│  ├─ presentation/
│  │  ├─ main_window.py
│  │  ├─ pages/
│  │  ├─ widgets/
│  │  └─ generated_ui/
│  ├─ application/
│  │  ├─ commands/
│  │  ├─ queries/
│  │  ├─ services/
│  │  ├─ tasks/
│  │  └─ orchestrator.py
│  ├─ domain/
│  │  ├─ entities.py
│  │  ├─ relations.py
│  │  ├─ enums.py
│  │  └─ events.py
│  ├─ infrastructure/
│  │  ├─ db/
│  │  ├─ parsers/
│  │  ├─ llm/
│  │  ├─ embeddings/
│  │  ├─ search/
│  │  ├─ scheduler/
│  │  ├─ storage/
│  │  └─ connectors/
│  └─ shared/
│     ├─ logging.py
│     ├─ config.py
│     └─ result.py
├─ tests/
├─ data/
└─ migrations/
```

## 3. 分层边界

### Presentation
只负责显示和采集用户动作。页面不得直接调用模型或写数据库。

### Application
执行用例：创建论文、导入版本、整理 Idea、恢复上下文、更新投稿状态。

### Domain
保存实体、关系、状态机和领域规则。不得依赖 PySide6、模型 SDK 或数据库实现。

### Infrastructure
实现文件解析、SQLite、LLM、向量检索、定时器和外部连接器。

## 4. 首版对象

- Paper
- PaperVersion
- Idea
- Note
- SourceDocument
- Submission
- Conference
- Task
- EvidenceRef
- EntityRelation
- AuditLog
- DomainEvent

基金对象可预留但无需首版页面。

## 5. 核心接口

只抽象八类：

1. DocumentParser
2. LLMProvider
3. EmbeddingProvider
4. SearchProvider
5. TaskExecutor
6. EventBus
7. ExternalConnector
8. ExportProvider

不要为每个页面和按钮创建无意义接口。

## 6. 上下文恢复流水线

```text
RecoverContextCommand
  -> load Paper and current version
  -> query explicit relations
  -> retrieve recent changes and deleted candidates
  -> keyword + semantic search
  -> build evidence bundle
  -> LLM structured synthesis
  -> validate source references
  -> save ContextRecoverySnapshot
  -> publish context.recovered
```

结构化输出必须符合 JSON Schema，不允许自由文本直接写入数据库。

## 7. 增量文件监控

- 首次导入允许全量扫描指定目录。
- 后续基于路径、mtime、size 和 sha256 判断变化。
- 已处理文件写入 `file_index`。
- 不得在每个周期遍历并解析全部文件。
- 支持用户选择“从现在开始”或“扫描指定历史时间”。

## 8. 多 Agent 预留

MVP：`LocalOrchestrator + TaskExecutorRegistry`。

未来：

```text
Orchestrator
├─ Document Agent
├─ Knowledge Agent
├─ Revision Agent
├─ Submission Agent
├─ Conference Agent
└─ Grant Agent
```

各 Agent 只能通过 TaskContract 获取任务，通过 EventBus 发布结果；不得直接互相修改状态。共享状态以数据库为准。

## 9. 权限策略

- Parser：读取原文件，写解析产物
- Knowledge：写候选 Idea 和关系，不覆盖用户确认数据
- Context Recovery：只读聚合，写快照
- Submission：写投稿状态，必须保留历史
- Grant：只生成建议
- 原始文件：任何模块均不可覆盖

## 10. 错误处理

所有服务返回统一 Result：

```json
{
  "ok": false,
  "error_code": "PARSER_UNSUPPORTED_FORMAT",
  "message": "...",
  "retryable": false,
  "details": {}
}
```

模型失败不得导致数据回滚失败；AI 任务与确定性导入事务分离。

## 11. 测试优先级

1. 文件不会被覆盖
2. 同一文件不会重复导入
3. 版本关系可纠正
4. Idea 可关联多篇论文
5. 上下文恢复中的每条结论都有 EvidenceRef
6. 所有自动关系可撤销
7. 定期扫描为增量执行
8. Provider 替换不影响上层用例
