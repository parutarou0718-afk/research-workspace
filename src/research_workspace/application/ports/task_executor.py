"""Task-executor contract boundary; no executor implementation in v0.1."""

from typing import Protocol

from research_workspace.domain.tasks import TaskContract, TaskResult


class TaskExecutor(Protocol):
    """Dormant contract for a future fenced executor."""

    supported_task_types: set[str]

    def execute(self, task: TaskContract) -> TaskResult:
        raise NotImplementedError
