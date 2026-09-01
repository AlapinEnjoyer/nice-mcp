"""Application and build configuration."""

from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrieverMode(StrEnum):
    """Retrieval strategies selectable at runtime."""

    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="NICE_MCP_", frozen=True)

    # snapshot_path: Path = Path("data/current") # Will probably use snapshots and avoid using a vector db
    retriever: RetrieverMode = RetrieverMode.HYBRID
    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated runtime settings."""
    return Settings()
