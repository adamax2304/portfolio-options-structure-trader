from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_local_env(path: Path | None = None) -> None:
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value


class Settings:
    def __init__(self, data: dict[str, Any], root: Path = PROJECT_ROOT):
        self.data = _expand_env(data)
        self.root = root
        canonical = json.dumps(self.data, sort_keys=True, separators=(",", ":"))
        self.version = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        load_local_env()
        config_path = Path(path) if path else PROJECT_ROOT / "config" / "config.yaml"
        with config_path.open("r", encoding="utf-8") as handle:
            return cls(yaml.safe_load(handle), config_path.parent.parent)

    def section(self, name: str) -> dict[str, Any]:
        return self.data.get(name, {})

    def get(self, dotted: str, default: Any = None) -> Any:
        current: Any = self.data
        for part in dotted.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def path(self, dotted: str) -> Path:
        value = Path(str(self.get(dotted)))
        return value if value.is_absolute() else self.root / value
