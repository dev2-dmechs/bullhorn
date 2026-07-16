from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create the schema and seed the two tenants. Runs at startup.

    There is no Alembic here by choice. `create_all` only ever CREATES missing tables — it
    will not ALTER an existing one. So if a column is ever added to `Company`, the change
    will silently not appear in a database that already has the table, and it must be
    applied by hand (or the table dropped and recreated).
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                "INSERT INTO companies (id, name) "
                "VALUES ('A', 'Company A'), ('B', 'Company B') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
