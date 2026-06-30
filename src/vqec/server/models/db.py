from enum import Enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from vqec.server.utils import utc_now

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ExperimentTask(SQLModel, table=True):
    __tablename__ = "experiment_task"
    __table_args__ = (
        Index("ix_experimenttask_created_at_desc", text("created_at DESC")),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    config_hash: str = Field(unique=True, index=True)
    config_json: str
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    error_message: Optional[str] = Field(default=None)
    parquet_results_path: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class DataGenerationTask(SQLModel, table=True):
    __tablename__ = "data_generation_task"

    id: Optional[int] = Field(default=None, primary_key=True)
    config_hash: str = Field(unique=True, index=True)
    spec_json: str
    status: TaskStatus = Field(default=TaskStatus.PENDING, index=True)
    error_message: Optional[str] = Field(default=None)
    outcome_file_path: Optional[str] = Field(default=None)
    leased_until: Optional[datetime] = Field(default=None)
    shots: Optional[int] = Field(default=None)
    time_build_circuit_s: Optional[float] = Field(default=None)
    time_apply_noise_s: Optional[float] = Field(default=None)
    time_runner_run_s: Optional[float] = Field(default=None)
    time_pickle_write_s: Optional[float] = Field(default=None)
    metadata_json: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class DecodingTask(SQLModel, table=True):
    __tablename__ = "decoding_task"
    __table_args__ = (
        Index("ix_decodingtask_status_requires_gpu", "status", "requires_gpu"),
        Index("ix_decodingtask_experiment_id_status", "experiment_id", "status"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    experiment_id: int = Field(foreign_key="experiment_task.id", ondelete="CASCADE")
    data_generation_task_id: int = Field(foreign_key="data_generation_task.id", index=True)
    requires_gpu: bool
    spec_json: str
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    error_message: Optional[str] = Field(default=None)
    leased_until: Optional[datetime] = Field(default=None)
    logical_error_rate: Optional[float] = Field(default=None)
    n_errors: Optional[int] = Field(default=None)
    time_decoder_setup_s: Optional[float] = Field(default=None)
    time_decoder_decode_s: Optional[float] = Field(default=None)
    time_total_s: Optional[float] = Field(default=None)
    metadata_json: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
