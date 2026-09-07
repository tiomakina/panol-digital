"""
Motor async de base de datos con SQLAlchemy 2.0 + filtro automático por tenant.

El filtro de tenant funciona de la siguiente manera:
1. TenantMiddleware (main.py) lee la cookie panol_tenant y llama a
   set_current_tenant() al inicio de cada petición.
2. get_db() crea una sesión AsyncSession y le registra dos eventos:
   - do_orm_execute: agrega WHERE tenant_id = :tenant a todos los SELECT
     ORM sobre modelos que hereden de TenantMixin.
   - before_flush: auto-asigna tenant_id a todos los objetos nuevos
     (INSERT) que hereden de TenantMixin y no tengan el campo todavía.
3. Las operaciones de sistema (seeds, migraciones) pueden omitir el filtro
   pasando execution_options={"skip_tenant_filter": True} al execute().
"""
from typing import AsyncGenerator, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, with_loader_criteria
from sqlalchemy.pool import StaticPool

from app.core.config import settings

_engine_kwargs: dict = {"echo": settings.DEBUG}

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


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _configure_tenant_session(session: AsyncSession, tenant_id: Optional[str]) -> None:
    """
    Registra los dos eventos de aislamiento de tenant en la sesión dada.
    Llamado por get_db() una vez que conoce el tenant activo.
    """
    from app.core.tenant import SKIP_TENANT_FILTER_KEY
    from app.models.tenant_mixin import TenantMixin

    sync_session = session.sync_session

    @event.listens_for(sync_session, "do_orm_execute")
    def _add_tenant_criteria(orm_execute_state):
        """
        Intercepta todos los SELECT ORM y agrega WHERE tenant_id = :tenant
        para modelos que hereden de TenantMixin, a menos que el execute
        lleve la opción skip_tenant_filter=True.
        """
        if (
            tenant_id is None
            or orm_execute_state.is_column_load
            or orm_execute_state.is_relationship_load
            or orm_execute_state.execution_options.get(SKIP_TENANT_FILTER_KEY, False)
        ):
            return

        # with_loader_criteria agrega el filtro a la carga de la entidad
        # (tanto el SELECT principal como lazy-loads relacionados).
        orm_execute_state.statement = orm_execute_state.statement.options(
            with_loader_criteria(
                TenantMixin,
                lambda cls: cls.tenant_id == tenant_id,  # type: ignore[attr-defined]
                include_aliases=True,
            )
        )

    @event.listens_for(sync_session, "before_flush")
    def _set_tenant_on_new_objects(session_obj, flush_context, instances):
        """
        Auto-asigna tenant_id en los objetos nuevos (INSERT) que hereden
        de TenantMixin y no tengan ya un valor asignado.
        """
        if tenant_id is None:
            return
        for obj in session_obj.new:
            if isinstance(obj, TenantMixin) and not getattr(obj, "tenant_id", None):
                obj.tenant_id = tenant_id  # type: ignore[attr-defined]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia FastAPI que produce una sesión de base de datos aislada
    por tenant. El tenant se lee de la ContextVar seteada por el middleware.
    """
    # Import aquí (no al módulo) para evitar el import circular con tenant.py
    from app.core.tenant import get_current_tenant

    tenant_id = get_current_tenant()

    async with AsyncSessionLocal() as session:
        _configure_tenant_session(session, tenant_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_superuser_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Sesión de base de datos SIN filtro de tenant — solo para operaciones
    de sistema: seeds, migraciones, tareas Celery cross-tenant.
    Nunca exponer esta dependencia en endpoints públicos.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
