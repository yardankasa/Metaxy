from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource


class PoolSettings(BaseModel):
    sweep_interval_seconds: float = 30.0
    concurrency: int = 10
    timeout_seconds: float = 8.0


class EgressSettings(BaseModel):
    proxy_url: str = ""
    interval_seconds: float = 20.0
    timeout_seconds: float = 10.0


class FeederSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 18080
    connect_timeout_seconds: float = 5.0
    max_failover: int = 8


class ApiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080


class ScoringSettings(BaseModel):
    weight_success_1h: float = 0.35
    weight_success_24h: float = 0.20
    weight_success_7d: float = 0.15
    weight_healthy: float = 0.10
    weight_latency: float = 0.20
    latency_ref_ms: float = 2000.0


class SelectionSettings(BaseModel):
    fail_threshold: int = 2
    success_threshold: int = 1
    score_switch_margin: float = 0.05
    switch_hold_sweeps: int = 1


class StoreSettings(BaseModel):
    path: str = "data/health.sqlite"
    cache_kb: int = 8192


class MemorySettings(BaseModel):
    max_rss_mb: int = 384
    hard_limit_mb: int = 0
    max_connections: int = 64
    max_probe_body_bytes: int = 8192
    checks_retain_days: int = 8
    check_interval_seconds: float = 15.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="METAXY_",
        env_nested_delimiter="__",
        extra="ignore",
        env_file=".env",
        yaml_file="config.yaml",
    )

    check_url: str = "http://www.gstatic.com/generate_204"
    expected_status: int = 204
    inventory_path: str = "proxies.yaml"
    pool: PoolSettings = Field(default_factory=PoolSettings)
    egress: EgressSettings = Field(default_factory=EgressSettings)
    feeder: FeederSettings = Field(default_factory=FeederSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    selection: SelectionSettings = Field(default_factory=SelectionSettings)
    store: StoreSettings = Field(default_factory=StoreSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    @field_validator("check_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("check_url must be an http(s) URL")
        return value

    def store_file(self, root: Path) -> Path:
        path = Path(self.store.path)
        return path if path.is_absolute() else root / path

    def inventory_file(self, root: Path) -> Path:
        path = Path(self.inventory_path)
        return path if path.is_absolute() else root / path


def load_settings(config_path: Path | None = None) -> Settings:
    if config_path is None:
        return Settings()

    class FileSettings(Settings):
        model_config = SettingsConfigDict(
            env_prefix="METAXY_",
            env_nested_delimiter="__",
            extra="ignore",
            yaml_file=str(config_path),
        )

    return FileSettings()
