"""
Pruebas de la API de respaldo — permisos y el flujo completo (crear,
listar, descargar, restaurar), con pg_dump/psql mockeados: la suite corre
contra SQLite en memoria, así que invocar los binarios reales de Postgres
acá no tiene sentido (eso se probó a mano contra Postgres real, igual que
las migraciones).
"""
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.services import backup_service


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


def _patch_backup_io(monkeypatch, tmp_path):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup_service, "UPLOAD_DIR", tmp_path / "uploads")
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "dummy.txt").write_text("archivo de prueba")

    async def fake_run(cmd, *, env, stdin_bytes=None):
        if cmd[0] == "pg_dump":
            return b"-- dump falso generado por el mock del test\n"
        if cmd[0] == "psql":
            return b""
        raise AssertionError(f"comando inesperado: {cmd}")

    monkeypatch.setattr(backup_service, "_run", fake_run)


async def test_only_jefe_can_use_backup_endpoints(client, tmp_path, monkeypatch):
    _patch_backup_io(monkeypatch, tmp_path)
    await _create_user("encargado_bk@test.com", "Clave123!", UserRole.encargado)
    token = await _login(client, "encargado_bk@test.com", "Clave123!")

    assert (await client.get("/api/v1/backup", headers=_auth(token))).status_code == 403
    assert (await client.post("/api/v1/backup", headers=_auth(token))).status_code == 403


async def test_full_backup_and_restore_flow(client, tmp_path, monkeypatch):
    _patch_backup_io(monkeypatch, tmp_path)
    await _create_user("jefe_bk@test.com", "ClaveJefe123!", UserRole.jefe)
    token = await _login(client, "jefe_bk@test.com", "ClaveJefe123!")

    created = await client.post("/api/v1/backup", headers=_auth(token))
    assert created.status_code == 200, created.text
    name = created.json()["name"]
    assert created.json()["database_size"] > 0

    listed = await client.get("/api/v1/backup", headers=_auth(token))
    assert any(b["name"] == name for b in listed.json())

    downloaded = await client.get(f"/api/v1/backup/{name}/download", headers=_auth(token))
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"

    # Restaurar con la contraseña equivocada no pasa
    wrong_pw = await client.post(
        f"/api/v1/backup/{name}/restore", json={"current_password": "incorrecta"}, headers=_auth(token)
    )
    assert wrong_pw.status_code == 400

    restored = await client.post(
        f"/api/v1/backup/{name}/restore", json={"current_password": "ClaveJefe123!"}, headers=_auth(token)
    )
    assert restored.status_code == 200, restored.text


async def test_restore_rejects_unknown_backup_name(client, tmp_path, monkeypatch):
    _patch_backup_io(monkeypatch, tmp_path)
    await _create_user("jefe_bk2@test.com", "ClaveJefe123!", UserRole.jefe)
    token = await _login(client, "jefe_bk2@test.com", "ClaveJefe123!")

    res = await client.post(
        "/api/v1/backup/../../etc/restore", json={"current_password": "ClaveJefe123!"}, headers=_auth(token)
    )
    # FastAPI ya normaliza el path, así que esto puede dar 404 (ruta no
    # encontrada) o 400 (BackupError por nombre inválido) según cómo lo
    # resuelva el router — cualquiera de los dos es "no lo dejó pasar".
    assert res.status_code in (400, 404)

    clean = await client.post(
        "/api/v1/backup/no_existe_este_backup/restore",
        json={"current_password": "ClaveJefe123!"},
        headers=_auth(token),
    )
    assert clean.status_code == 400


async def test_upload_backup_requires_database_sql(client, tmp_path, monkeypatch):
    _patch_backup_io(monkeypatch, tmp_path)
    await _create_user("jefe_bk3@test.com", "ClaveJefe123!", UserRole.jefe)
    token = await _login(client, "jefe_bk3@test.com", "ClaveJefe123!")

    res = await client.post(
        "/api/v1/backup/upload",
        files={"file": ("backup.zip", b"esto no es un zip valido", "application/zip")},
        headers=_auth(token),
    )
    assert res.status_code == 400
