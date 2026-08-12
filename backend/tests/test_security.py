"""Pruebas unitarias de JWT: creación, decodificación, tipos y revocación."""
import pytest
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_token_revoked,
    revoke_token,
)


def test_access_token_roundtrip():
    token = create_access_token(user_id=7, role="jefe")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "7"
    assert payload["role"] == "jefe"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token(user_id=7)
    payload = decode_token(token, expected_type="refresh")
    assert payload["type"] == "refresh"


def test_decode_rejects_wrong_type():
    token = create_refresh_token(user_id=1)
    with pytest.raises(HTTPException) as exc:
        decode_token(token, expected_type="access")
    assert exc.value.status_code == 401


def test_decode_rejects_garbage_token():
    with pytest.raises(HTTPException):
        decode_token("esto-no-es-un-jwt")


@pytest.mark.asyncio
async def test_revoke_token_marks_as_revoked():
    token = create_access_token(user_id=3, role="mecanico")
    payload = decode_token(token, expected_type="access")

    assert await is_token_revoked(payload) is False
    await revoke_token(payload)
    assert await is_token_revoked(payload) is True
