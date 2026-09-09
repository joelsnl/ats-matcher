from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llama_model_path: Path | None = Field(default=None, validation_alias="LLAMA_MODEL_PATH")
    llama_n_gpu_layers: int = Field(default=-1, validation_alias="LLAMA_N_GPU_LAYERS")
    llama_n_ctx: int = Field(default=8192, validation_alias="LLAMA_N_CTX")
    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    jobs_provider: str = Field(default="linkedin", validation_alias="JOBS_PROVIDER")


def get_settings() -> Settings:
    return Settings()
