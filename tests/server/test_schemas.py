import pytest
from pydantic import ValidationError

from vqec.server.models.db import TaskStatus
from vqec.server.models.schemas import WorkerCompleteRequest


def test_worker_complete_request_rejects_invalid_type():
    with pytest.raises(ValidationError):
        WorkerCompleteRequest(type="invalid", id=1, status=TaskStatus.COMPLETED)


def test_worker_complete_request_accepts_valid_types():
    req = WorkerCompleteRequest(type="decoding", id=1, status=TaskStatus.COMPLETED)
    assert req.type == "decoding"
