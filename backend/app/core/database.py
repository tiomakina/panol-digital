"""Motor async de base de datos con SQLAlchemy 2.0."""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from app.core.config import settings

_engine_kwargs = {"echo": settings.DEBUG}

if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite (usado en la suite de tests) no acepta pool_size/max_overflow.
    # Para bases ":memory:" se necesita StaticPool para compartir la misma
    # conexión entre sesiones — de lo contrario cada una ve una BD vacía.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.DATABASE_URL:
        _engine_kwargs["poolclass"] = StaticPool
else:
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def create_tables():
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
