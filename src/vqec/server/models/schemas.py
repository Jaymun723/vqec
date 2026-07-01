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

class ExperimentRead(BaseModel):
    id: int
    name: str
    config_hash: str
    status: TaskStatus
    error: Optional[str] = None
    result_path: Optional[str] = None
    submitted_at: datetime
    completed_at: Optional[datetime] = None
    progress: Optional[float] = None
    jobs_done: Optional[int] = None
    jobs_total: Optional[int] = None


class ExperimentDetail(ExperimentRead):
    config: Dict[str, Any]


class ExperimentDeletedRead(BaseModel):
    id: int
    name: str
    config_hash: str
    status: str = "deleted"
