from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

sessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    # each request gets its own session so db calls don't bleed into each other
    async with sessionLocal() as session:
        yield session


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    # streaming responses outlive the request session, so they open their own
    return sessionLocal


DbSession = Annotated[AsyncSession, Depends(get_db)]
SessionMaker = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
