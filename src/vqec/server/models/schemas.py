from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any, Dict
from datetime import datetime
from vqec.server.models.db import TaskStatus

# System & Registry Schemas


class SystemInfo(BaseModel):
    name: str
    version: str
    status: str
    documentation: str
    registry: str


class RegistryComponent(BaseModel):
    model_config = {"populate_by_name": True}

    name: str
    description: str
    schema_: Dict[str, Any] = Field(alias="schema")
    compatibility: Dict[str, List[str]]


class ValidateExperimentRequest(BaseModel):
    config: Dict[str, Any]


class ValidateExperimentResponse(BaseModel):
    valid: bool
    jobs_count: int
    error: Optional[str] = None


# Task Schemas


class DecodingTaskRead(BaseModel):
    id: int
    status: TaskStatus
    logical_error_rate: Optional[float] = None
    n_errors: Optional[int] = None
    time_total_s: Optional[float] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ExperimentTaskRead(BaseModel):
    id: int
    name: str
    config_hash: str
    status: TaskStatus
    completed_jobs: int
    total_jobs: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ExperimentTaskDetail(ExperimentTaskRead):
    config: Dict[str, Any]
    jobs: List[DecodingTaskRead]


class ExperimentTaskDeletedRead(BaseModel):
    id: int
    name: str
    config_hash: str
    status: str = "deleted"


# Worker Schemas


class WorkerPollRequest(BaseModel):
    batch_size: int = Field(default=10)
    has_gpu: bool = False


class WorkerTaskSpec(BaseModel):
    type: str
    id: int
    data_id: Optional[int] = None
    spec: Dict[str, Any]
    data_spec: Optional[Dict[str, Any]] = None


class WorkerPollResponse(BaseModel):
    tasks: List[WorkerTaskSpec]


class WorkerHeartbeatRequest(BaseModel):
    task_ids: List[int]


class WorkerStatusResponse(BaseModel):
    status: str = "ok"


class DecodingMetrics(BaseModel):
    logical_error_rate: float
    n_errors: int
    time_decoder_setup_s: float
    time_decoder_decode_s: float
    time_total_s: float


class WorkerCompleteRequest(BaseModel):
    type: str
    id: int
    status: TaskStatus
    metrics: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in ("data_generation", "decoding"):
            raise ValueError("type must be 'data_generation' or 'decoding'")
        return value
