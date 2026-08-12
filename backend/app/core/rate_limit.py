"""Rate limiting para endpoints sensibles (login, etc.) con ventana fija en Redis."""
from fastapi import HTTPException, Request, status
from app.core import redis_client as redis_client_module


def rate_limiter(key_prefix: str, max_attempts: int = 5, window_seconds: int = 300):
    """
    Devuelve una dependencia FastAPI que limita los intentos por IP en una ventana de tiempo fija.
    Ej: rate_limiter("login", max_attempts=5, window_seconds=300) → 5 intentos cada 5 minutos.
    """
    async def limiter(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{key_prefix}:{client_ip}"

        attempts = await redis_client_module.redis_client.incr(key)
        if attempts == 1:
            await redis_client_module.redis_client.expire(key, window_seconds)

        if attempts > max_attempts:
            ttl = await redis_client_module.redis_client.ttl(key)
            wait = ttl if ttl and ttl > 0 else window_seconds
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos. Intente nuevamente en {wait} segundos.",
            )

    return limiter
