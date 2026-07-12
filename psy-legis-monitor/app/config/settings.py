"""Runtime settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_URL = "sqlite:///psy_legis_monitor.db"


class AppSettings(BaseModel):
    """Validated application settings.

    SQLite is the zero-configuration default so Streamlit Community Cloud can
    boot without external services. Set DATABASE_URL to use PostgreSQL.
    """

    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    keywords_path: Path = CONFIG_DIR / "keywords.yml"
    sources_path: Path = CONFIG_DIR / "sources.yml"
    taxonomy_path: Path = CONFIG_DIR / "taxonomy.yml"

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                DEFAULT_DATABASE_URL,
            ),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            keywords_path=Path(os.getenv("KEYWORDS_PATH", CONFIG_DIR / "keywords.yml")),
            sources_path=Path(os.getenv("SOURCES_PATH", CONFIG_DIR / "sources.yml")),
            taxonomy_path=Path(os.getenv("TAXONOMY_PATH", CONFIG_DIR / "taxonomy.yml")),
        )


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return an empty mapping for blank files."""

    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


settings = AppSettings.from_env()
