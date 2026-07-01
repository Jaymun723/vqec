import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient
from vqec.server.main import app, lifespan
from vqec.server.database import get_session
import sys

pytestmark = pytest.mark.asyncio

async def test_lifespan_and_get_session(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr("vqec.server.main.Client", AsyncMock())
    
    try:
        async with lifespan(app):
            pass
    except Exception as e:
        pytest.fail(f"Lifespan failed: {e}")

    gen = get_session()
    session = await anext(gen)
    assert session is not None
    try:
        await anext(gen)
    except StopAsyncIteration:
        pass

async def test_init_db():
    from vqec.server.database import init_db
    await init_db()
