"""Application and build configuration."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrieverMode(StrEnum):
    """Retrieval strategies selectable at runtime."""

    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="NICE_MCP_", frozen=True)

    snapshot_path: Path = Path("data/current")
    dense_device: str = "cpu"
    retriever: RetrieverMode = RetrieverMode.HYBRID
    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated runtime settings."""
    return Settings()


class BuildConfig(BaseModel):
    """Deterministic corpus-build configuration."""

    model_config = ConfigDict(frozen=True)

    source_index_url: str = "https://nicegui.io/static/search_index.json"
    preferred_tokens: int = 450
    hard_tokens: int = 500
    tokenizer: str = "BAAI/bge-small-en-v1.5"
