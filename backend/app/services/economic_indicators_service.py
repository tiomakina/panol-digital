"""
Servicio de indicadores económicos de Chile (dólar, UF, euro, UTM) — se
muestran en el header. Los trae de mindicador.cl (API pública, sin
autenticación) y los cachea en Redis unas horas: no hace falta pedirlos en
cada request, y si la API externa está caída o no hay salida a internet,
se sigue mostrando el último valor conocido en vez de romper el header.
"""
import json
from datetime import datetime, timezone

import httpx

import app.core.redis_client as redis_client_module

MINDICADOR_URL = "https://mindicador.cl/api"
CACHE_KEY = "economic_indicators:cl"
CACHE_TTL_SECONDS = 4 * 60 * 60  # 4 horas — no son valores que cambien minuto a minuto

# Qué indicadores mostramos y en qué orden — mindicador.cl trae más (ipc,
# imacec, tpm, etc.) pero el pedido puntual fue dólar/UF/euro/UTM.
_INDICATOR_KEYS = ("dolar", "uf", "euro", "utm")


async def _fetch_from_api() -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(MINDICADOR_URL)
            res.raise_for_status()
            data = res.json()
    except (httpx.HTTPError, ValueError):
        return None

    indicators = {}
    for key in _INDICATOR_KEYS:
        entry = data.get(key)
        if entry and "valor" in entry:
            indicators[key] = {"valor": entry["valor"], "fecha": entry.get("fecha")}
    return indicators or None


async def get_indicators() -> dict:
    """
    Devuelve {"dolar": {...}, "uf": {...}, ...} + "cached_at". Si la API
    externa no responde, cae al último valor guardado en Redis (aunque
    esté vencido) antes de devolver vacío — un header sin datos frescos es
    mejor que uno roto.
    """
    redis = redis_client_module.redis_client
    cached_raw = await redis.get(CACHE_KEY)
    if cached_raw:
        cached = json.loads(cached_raw)
        fetched_at = datetime.fromisoformat(cached["cached_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if age < CACHE_TTL_SECONDS:
            return cached

    fresh = await _fetch_from_api()
    if fresh:
        payload = {**fresh, "cached_at": datetime.now(timezone.utc).isoformat()}
        await redis.set(CACHE_KEY, json.dumps(payload), ex=CACHE_TTL_SECONDS * 6)
        return payload

    # La API externa falló — mostramos lo último que tengamos guardado,
    # aunque esté vencido, en vez de un header vacío.
    if cached_raw:
        return json.loads(cached_raw)

    return {"cached_at": None}
