# Gate 1 确定性接口台账

本文件是 v0.2 Gate 1 的接口合同。应用层先验证请求、权限和冻结工作计划；专用 worker 只执行获批的受限 I/O 或计算并返回不可变 DTO；统一写协调器才可持久化事实和 DomainEvent。

## 外层 actor 边界

原始请求的 `actor_type` 必须在构造 `PermissionContext` 之前验证。`agent` 和 `task_executor` 立即返回 `ACTOR_NOT_ENABLED`，且不得创建 staging、恢复点、数据库事务或事件。`PermissionContext 1.0` 只允许 `user | system`，历史权限快照不是可重放凭证。

## 固定 DTO

```python
@dataclass(frozen=True)
class PathScope:
    scope_type: Literal["import_source", "snapshot_read", "workspace_staging"]
    normalized_path_hash: str
    root_id: UUID
    access_mode: Literal["read", "list", "copy", "create_only"]
    recursive: bool

@dataclass(frozen=True)
class PermissionContext:
    schema_version: Literal["1.0"]
    actor_type: Literal["user", "system"]
    actor_id: str | None
    workspace_id: UUID
    capabilities: tuple[str, ...]
    scope_refs: tuple[str, ...]
    path_scopes: tuple[PathScope, ...]
    network_allowed: Literal[False]
    granted_at: datetime
    policy_version: str
    authorization_decision_id: UUID

@dataclass(frozen=True)
class FileStat:
    size_bytes: int
    modified_time_ns: int
    file_id_hint: str | None
    volume_serial_hint: str | None

@dataclass(frozen=True)
class ImportRequest:
    source_paths: tuple[Path, ...]
    permission_context: PermissionContext

@dataclass(frozen=True)
class StagedSource:
    source_path: Path
    staging_path: Path
    sha256: str
    size_bytes: int
    pre_stat: FileStat
    post_stat: FileStat

@dataclass(frozen=True)
class ParseRequest:
    parse_artifact_id: UUID
    snapshot_id: UUID
    snapshot_path: Path
    snapshot_sha256: str
    mime_type: str
    parser_config: Mapping[str, object]

@dataclass(frozen=True)
class ParseResult:
    parsed_document: Mapping[str, object] | None
    warning_codes: tuple[str, ...]
    error_code: str | None

@dataclass(frozen=True)
class SnapshotRegistrationDTO:
    operation_id: UUID
    batch_id: UUID
    import_item_id: UUID
    source_observation_id: UUID
    snapshot_id: UUID
    source_path: Path
    original_filename: str
    sha256: str
    size_bytes: int
    mime_type: str
    storage_relative_path: str
    duplicate_content: bool

@dataclass(frozen=True)
class ImportCommitDTO:
    snapshot_id: UUID
    source_observation_id: UUID
    import_item_id: UUID
    state: Literal["imported", "duplicate_content"]

@dataclass(frozen=True)
class ImportBatchResult:
    batch_id: UUID
    operation_id: UUID
    item_results: tuple[ImportCommitDTO, ...]
    failed_item_ids: tuple[UUID, ...]
    cancelled_item_ids: tuple[UUID, ...]

@dataclass(frozen=True)
class ParseSuccessDTO:
    operation_id: UUID
    parse_artifact_id: UUID
    parse_attempt_id: UUID
    parsed_document: Mapping[str, object]
    output_sha256: str
    derived_file_sha256: str
    derived_relative_path: str

@dataclass(frozen=True)
class ParseFailureDTO:
    operation_id: UUID
    parse_artifact_id: UUID
    parse_attempt_id: UUID
    error_code: str
    warning_codes: tuple[str, ...]
```

跨端口前，tuple 和 mapping 必须已冻结并规范化；DTO 不授予额外路径、网络或数据库权限。

## Application Ports

```python
class FilesystemPort(Protocol):
    def validate_source(self, source: Path, allowed_scope: PathScope) -> None: ...
    def stage_stable_copy(self, source: Path, staging_dir: Path) -> StagedSource: ...
    def promote_snapshot(self, staged: StagedSource, sources_root: Path) -> Path: ...

class DocumentParser(Protocol):
    parser_id: str
    parser_version: str
    supported_mime_types: frozenset[str]
    def parse(self, request: ParseRequest) -> ParseResult: ...

class WriteCoordinator(Protocol):
    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO: ...
    def register_parse_success(self, result: ParseSuccessDTO) -> None: ...
    def register_parse_failure(self, result: ParseFailureDTO) -> None: ...
```

worker 不得持有 SQLAlchemy Session、QWidget 或 Qt model，不得发布正式 DomainEvent，也不得扩大冻结工作计划。Gate 1 的内置工作流固定 `network_allowed=false`。

## 保留但关闭的未来合同

TaskContract 1.0、TaskResult 1.0 和 DomainEvent 1.0 仅保持读取与 Schema 兼容。Gate 1 不启用通用 TaskExecutor、Agent、LLM、Embedding、Search、Connector 或 Export runtime；所有新事件必须通过 DomainEvent 2.0 新写入口验证。
