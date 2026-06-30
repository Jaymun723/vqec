import pytest

from vqec.server.repositories.experiment import ExperimentRepository

pytestmark = pytest.mark.asyncio


async def test_delete_experiment_not_found(session):
    repo = ExperimentRepository(session)
    assert await repo.delete_experiment(99999) is False
