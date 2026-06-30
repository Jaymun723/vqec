from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class ServerConfig(BaseSettings):
    # Environment Variables based on operations.md
    database_url: str = Field(default="sqlite+aiosqlite:///data/vqec_server.db", alias="VQEC_DATABASE_URL")
    storage_dir: str = Field(default="data/storage", alias="VQEC_STORAGE_DIR")
    host: str = Field(default="0.0.0.0", alias="VQEC_HOST")
    port: int = Field(default=8000, alias="VQEC_PORT")
    log_level: str = Field(default="INFO", alias="VQEC_LOG_LEVEL")
    task_lease_seconds: int = Field(default=300, alias="VQEC_TASK_LEASE_SECONDS")
    max_upload_bytes: int = Field(default=536870912, alias="VQEC_MAX_UPLOAD_BYTES")
    cors_origins: str = Field(default="*", alias="VQEC_CORS_ORIGINS")
    export_worker: bool = Field(default=True, alias="VQEC_EXPORT_WORKER")
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = ServerConfig()
