"""Pruebas del servicio de indicadores económicos de Chile (dólar, UF, euro, UTM)."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.services import economic_indicators_service as svc


async def _create_user(email: str, password: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as db:
        db.add(User(email=email, full_name="Test", role=role, hashed_password=hash_password(password)))
        await db.commit()


async def _login(client, email, password) -> str:
    res = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


_FAKE_API_RESPONSE = {
    "dolar": {"valor": 950.5, "fecha": "2026-08-12T03:00:00.000Z"},
    "uf": {"valor": 38500.12, "fecha": "2026-08-12T03:00:00.000Z"},
    "euro": {"valor": 1030.0, "fecha": "2026-08-12T03:00:00.000Z"},
    "utm": {"valor": 66500.0, "fecha": "2026-08-01T03:00:00.000Z"},
    "ipc": {"valor": 0.4, "fecha": "2026-08-01T03:00:00.000Z"},  # no lo mostramos, pero la API lo trae
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _clear_cache_module_state():
    # No hay estado de módulo que limpiar más allá de Redis (fakeredis ya
    # se resetea por test vía el fixture autouse de conftest), pero lo
    # dejamos explícito por si el servicio suma caché en memoria más adelante.
    yield


async def test_fetches_and_caches_indicators(monkeypatch):
    async def fake_get(self, url):
        assert url == svc.MINDICADOR_URL
        return _FakeResponse(_FAKE_API_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await svc.get_indicators()
    assert result["dolar"]["valor"] == 950.5
    assert result["uf"]["valor"] == 38500.12
    assert result["euro"]["valor"] == 1030.0
    assert result["utm"]["valor"] == 66500.0
    assert "ipc" not in result  # solo mostramos los 4 pedidos
    assert result["cached_at"] is not None

    # Segunda llamada: no debería volver a pegarle a la API (usa el cache)
    async def fail_get(self, url):
        raise AssertionError("no debería llamar a la API de nuevo, tendría que usar el cache")

    monkeypatch.setattr(httpx.AsyncClient, "get", fail_get)
    cached_result = await svc.get_indicators()
    assert cached_result["dolar"]["valor"] == 950.5


async def test_falls_back_to_stale_cache_when_api_is_down():
    redis = __import__("app.core.redis_client", fromlist=["redis_client"]).redis_client
    stale_payload = {
        "dolar": {"valor": 900.0, "fecha": "2026-08-01T00:00:00.000Z"},
        "cached_at": (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat(),
    }
    await redis.set(svc.CACHE_KEY, json.dumps(stale_payload))

    async def broken_get(self, url):
        raise httpx.ConnectError("sin salida a internet")

    import httpx as httpx_module
    orig = httpx_module.AsyncClient.get
    httpx_module.AsyncClient.get = broken_get
    try:
        result = await svc.get_indicators()
    finally:
        httpx_module.AsyncClient.get = orig

    # Vencido igual sirve más que nada — mejor un valor viejo que un header vacío
    assert result["dolar"]["valor"] == 900.0


async def test_returns_empty_when_no_api_and_no_cache():
    async def broken_get(self, url):
        raise httpx.ConnectError("sin salida a internet")

    import httpx as httpx_module
    orig = httpx_module.AsyncClient.get
    httpx_module.AsyncClient.get = broken_get
    try:
        result = await svc.get_indicators()
    finally:
        httpx_module.AsyncClient.get = orig

    assert result == {"cached_at": None}


async def test_economic_indicators_endpoint_requires_login(client):
    res = await client.get("/api/v1/indicators/economic")
    assert res.status_code == 401


async def test_economic_indicators_endpoint_returns_data(client, monkeypatch):
    await _create_user("meca_ind@test.com", "Clave123!", UserRole.mecanico)
    token = await _login(client, "meca_ind@test.com", "Clave123!")

    # OJO: httpx.AsyncClient.get es un método de clase compartido — el
    # cliente de prueba (`client`, que le pega a la app vía ASGITransport)
    # es TAMBIÉN un AsyncClient, así que un monkeypatch ciego rompería sus
    # propios llamados. Solo interceptamos si la URL es la del servicio de
    # indicadores; todo lo demás sigue el camino real.
    original_get = httpx.AsyncClient.get

    async def fake_get(self, url, *args, **kwargs):
        if url == svc.MINDICADOR_URL:
            return _FakeResponse(_FAKE_API_RESPONSE)
        return await original_get(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    res = await client.get("/api/v1/indicators/economic", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["dolar"]["valor"] == 950.5
