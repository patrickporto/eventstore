from os import environ
from async_generator import yield_, async_generator
from aiopg.sa import create_engine
import aiopg
import pytest


@pytest.fixture
@async_generator
async def dbsession():
    conn = await aiopg.connect(
        user=environ.get('DATABASE_USER'),
        password=environ.get('DATABASE_PASSWORD'),
        database=environ.get('DATABASE_DATABASE'),
        host=environ.get('DATABASE_HOST', 'localhost'),
        port=environ.get('DATABASE_PORT', 5432),
    )
    await yield_(conn)
    conn.close()


@pytest.fixture
@async_generator
async def saconnection():
    engine = await create_engine(
        user=environ.get('DATABASE_USER'),
        password=environ.get('DATABASE_PASSWORD'),
        database=environ.get('DATABASE_DATABASE'),
        host=environ.get('DATABASE_HOST', 'localhost'),
        port=environ.get('DATABASE_PORT', 5432),
    )
    async with engine.acquire() as conn:
        async with conn.begin() as transaction:
            await yield_(conn)
            await transaction.rollback()
