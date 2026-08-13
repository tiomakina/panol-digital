"""
Configuración compartida de pytest.

Corre la suite de forma totalmente aislada, sin depender de Postgres ni
Redis reales: usa SQLite en memoria para la base de datos y fakeredis para
rate limiting / revocación de tokens. Ambos se fijan ANTES de importar
`app.*` para que la app arranque ya apuntando a ellos.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SECRET_KEY", "test_secret_key")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="panol_test_uploads_"))

import fakeredis
import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.core.redis_client as _redis_module

# server=fakeredis.FakeServer() es lo que da el aislamiento real: sin él,
# fakeredis.aioredis.FakeRedis() reutiliza un server en memoria COMPARTIDO
# por defecto entre todas las instancias del proceso — es decir que, aunque
# _fresh_fake_redis (ver más abajo) cree una instancia nueva en cada test,
# seguían pisando el mismo estado (p. ej. el contador del rate limiter de
# login se acumulaba entre tests y terminaba devolviendo 429 en tests que
# no tenían nada que ver entre sí).
_redis_module.redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True, server=fakeredis.FakeServer())

from app.core.database import Base, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_fake_redis():
    """
    fakeredis liga su cola interna al event loop de su primer uso. Cada test
    async corre en su propio loop (pytest-asyncio, modo function-scoped), así
    que se necesita una instancia nueva por test — si no, el segundo test
    revienta con "Queue is bound to a different event loop". security.py y
    rate_limit.py acceden al cliente vía el módulo (no vía import directo del
    nombre) para que este reemplazo se vea reflejado en todos lados.

    server=fakeredis.FakeServer() es igual de necesario acá que en la
    inicialización de arriba: sin él, todas las instancias del proceso
    comparten el mismo estado en memoria por defecto, y el aislamiento
    "una instancia nueva por test" queda solo de nombre.
    """
    _redis_module.redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True, server=fakeredis.FakeServer())


@pytest_asyncio.fixture()
async def client():
    """
    Cliente HTTP async contra la app (ASGITransport, sin sockets reales) con
    la base de datos limpia en cada test. Todo corre en el mismo event loop
    que el test (a diferencia de TestClient, que usa un loop propio en otro
    hilo) para evitar problemas de cross-loop con la conexión SQLite/fakeredis.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def pytest_sessionfinish(session, exitstatus):
    """
    Cierra el engine de SQLite al terminar toda la suite. aiosqlite corre un
    hilo interno no-daemon por conexión (_connection_worker_thread); si no se
    hace dispose(), ese hilo queda vivo y el proceso de pytest nunca termina.
    """
    import asyncio

    asyncio.run(engine.dispose())
