from __future__ import annotations

import json
from pathlib import Path

from image_generation_model_comparison_portal.models import AppConfig

CONFIG_DIR = Path.home() / ".image_generation_model_comparison_portal"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> AppConfig | None:
    if not CONFIG_FILE.exists():
        return None
    return AppConfig.from_dict(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))


def save_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
