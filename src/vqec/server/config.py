from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class ServerConfig(BaseSettings):
    # Environment Variables based on operations.md
    database_url: str = Field(default="sqlite+aiosqlite:///data/vqec_server.db", alias="VQEC_DATABASE_URL")
    storage_dir: str = Field(default="data/storage", alias="VQEC_STORAGE_DIR")
    host: str = Field(default="0.0.0.0", alias="VQEC_HOST")
    port: int = Field(default=8000, alias="VQEC_PORT")
    log_level: str = Field(default="INFO", alias="VQEC_LOG_LEVEL")
    cors_origins: str = Field(default="*", alias="VQEC_CORS_ORIGINS")
    dask_scheduler_address: str = Field(default="tcp://127.0.0.1:8786", alias="VQEC_DASK_SCHEDULER_ADDRESS")
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = ServerConfig()
