from enum import Enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from vqec.server.utils import utc_now


class TaskStatus(str, Enum):
    IN_FLIGHT = "IN_FLIGHT"
    DONE = "DONE"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class Experiment(SQLModel, table=True):
    __tablename__ = "experiment"
    __table_args__ = (
        Index("ix_experiment_submitted_at_desc", text("submitted_at DESC")),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    status: TaskStatus = Field(default=TaskStatus.IN_FLIGHT)
    submitted_at: datetime = Field(default_factory=utc_now)
    result_path: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)

    name: str
    config_json: str
    config_hash: str = Field(unique=True, index=True)


class DataCache(SQLModel, table=True):
    __tablename__ = "data_cache"

    task_hash: str = Field(primary_key=True)
    output_path: str
    metadata_json: str


class DecodeCache(SQLModel, table=True):
    __tablename__ = "decode_cache"

    task_hash: str = Field(primary_key=True)
    metadata_json: str
