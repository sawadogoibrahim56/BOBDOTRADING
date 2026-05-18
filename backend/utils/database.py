"""
BTF – Connexion Base de Données (Supabase / PostgreSQL)
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/btf_db"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,  # Supabase gère son propre pool
    connect_args={"server_settings": {"timezone": "UTC"}},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    from backend.models.models import (  # noqa: F401 – importer pour créer les tables
        User, UserApiKey, Portfolio, RiskProfile, TradeOrder,
        MarketData, AISignal, PhysicalMarketTrend, PaymentRequest,
        UserAlert, SystemLog, AdminSession,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
