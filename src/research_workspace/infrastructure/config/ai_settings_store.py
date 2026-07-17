"""Local JSON persistence for demo AI settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from platformdirs import user_config_dir

from research_workspace.application.ports.ai_provider import AISettings


CONFIG_FIELDS = frozenset(
    {"schema_version", "provider", "base_url", "api_key", "model"}
)


def default_ai_settings_path() -> Path:
    return Path(user_config_dir("ResearchWorkspace", "ResearchWorkspace")) / "ai-settings.json"


class JsonAISettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_ai_settings_path()).expanduser().resolve()

    def load(self) -> AISettings | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != CONFIG_FIELDS:
            raise ValueError("AI settings file has an unsupported shape")
        if payload["schema_version"] != "1.0":
            raise ValueError("Unsupported AI settings schema version")
        return AISettings(
            provider=payload["provider"],
            base_url=payload["base_url"],
            api_key=payload["api_key"],
            model=payload["model"],
        )

    def save(self, settings: AISettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "provider": settings.provider,
            "base_url": settings.base_url,
            "api_key": settings.api_key,
            "model": settings.model,
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        finally:
            temporary_path.unlink(missing_ok=True)
