# Provider 与扩展接口

## DocumentParser

```python
class DocumentParser(Protocol):
    parser_id: str
    parser_version: str
    supported_extensions: frozenset[str]

    def parse(self, source: Path) -> Mapping[str, object]:
        raise NotImplementedError
```

输出必须包含段落级稳定 ID、页码/章节（可获得时）、原始偏移和文件指纹。

## LLMProvider

```python
class LLMProvider(Protocol):
    provider_id: str
    def generate_structured(self, request: LLMRequest, schema: dict) -> dict: ...
```

## EmbeddingProvider

```python
class EmbeddingProvider(Protocol):
    dimension: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

## SearchProvider

```python
class SearchProvider(Protocol):
    def index(self, chunks: list[SearchChunk]) -> None: ...
    def search(self, query: SearchQuery) -> list[SearchHit]: ...
```

## TaskExecutor

```python
class TaskExecutor(Protocol):
    supported_task_types: set[str]
    def execute(self, task: TaskContract) -> TaskResult: ...
```

未来 Agent 仅需实现相同接口。

## EventBus

```python
class EventBus(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, event_type: str, handler: Callable) -> None: ...
```

## ExternalConnector

```python
class ExternalConnector(Protocol):
    connector_id: str
    def sync(self, cursor: str | None) -> SyncResult: ...
```

邮箱、日历、基金数据源、云盘均作为 Connector。

## ExportProvider

```python
class ExportProvider(Protocol):
    format_id: str
    def export(self, selection: ExportSelection, target: Path) -> Path: ...
```
