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
    llama_n_gpu_layers: int = Field(default=0, validation_alias="LLAMA_N_GPU_LAYERS")
    llama_n_ctx: int = Field(default=8192, validation_alias="LLAMA_N_CTX")
    jobs_provider: str = Field(default="linkedin", validation_alias="JOBS_PROVIDER")
    jobs_greenhouse_boards: str | None = Field(default=None, validation_alias="JOBS_GREENHOUSE_BOARDS")
    jobs_lever_boards: str | None = Field(default=None, validation_alias="JOBS_LEVER_BOARDS")
    jobs_ashby_boards: str | None = Field(default=None, validation_alias="JOBS_ASHBY_BOARDS")
    jobs_indeed_country: str = Field(default="usa", min_length=1, validation_alias="JOBS_INDEED_COUNTRY")
    jobs_timeout: float = Field(default=15.0, ge=1, le=60, validation_alias="JOBS_TIMEOUT")
    jobs_request_delay: float = Field(default=2.0, ge=0, le=30, validation_alias="JOBS_REQUEST_DELAY")
    jobs_retries: int = Field(default=2, ge=0, le=3, validation_alias="JOBS_RETRIES")
    jobs_max_pages: int = Field(default=8, ge=1, le=20, validation_alias="JOBS_MAX_PAGES")
    jobs_cache_ttl: int = Field(default=3600, ge=0, le=86400, validation_alias="JOBS_CACHE_TTL")
    jobs_fetch_descriptions: bool = Field(default=True, validation_alias="JOBS_FETCH_DESCRIPTIONS")
    jobs_translate: bool = Field(default=True, validation_alias="JOBS_TRANSLATE")
    jobs_translate_to: str = Field(default="en", validation_alias="JOBS_TRANSLATE_TO")



def get_settings() -> Settings:
    return Settings()
