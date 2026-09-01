"""Cliente Redis compartido — usado para rate limiting y revocación de tokens JWT."""
import redis.asyncio as redis
from app.core.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
