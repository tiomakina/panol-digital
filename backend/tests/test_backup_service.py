"""
Pruebas del servicio de respaldo — solo la lógica pura (empaquetado,
validación de nombres, subida). create_backup()/restore_backup() invocan
pg_dump/psql de verdad contra Postgres, así que esos se probaron a mano
contra la base real (igual que las migraciones) en vez de acá, donde la
suite corre contra SQLite en memoria.
"""
import io
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from app.services import backup_service


@pytest.fixture(autouse=True)
def _isolated_backup_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path / "backups")
    return tmp_path


def _make_backup_dir(name: str, *, with_uploads: bool = True) -> Path:
    target = backup_service.BACKUP_DIR / name
    target.mkdir(parents=True)
    (target / "database.sql").write_text("-- dump falso para la prueba\n")
    if with_uploads:
        with tarfile.open(target / "uploads.tar.gz", "w:gz") as tar:
            info = tarfile.TarInfo(name="uploads/logo.png")
            data = b"contenido falso"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return target


def test_list_backups_empty_when_dir_missing():
    assert backup_service.list_backups() == []


def test_list_backups_ignores_unrelated_directories(tmp_path):
    backup_service.BACKUP_DIR.mkdir(parents=True)
    (backup_service.BACKUP_DIR / "no_es_un_backup").mkdir()
    _make_backup_dir("20260101_120000")

    backups = backup_service.list_backups()
    assert len(backups) == 1
    assert backups[0].name == "20260101_120000"
    assert backups[0].database_size > 0
    assert backups[0].uploads_size > 0


def test_validated_backup_dir_rejects_path_traversal():
    backup_service.BACKUP_DIR.mkdir(parents=True)
    for bad_name in ("../../etc", "20260101_120000/../../etc", "no_matches_pattern"):
        with pytest.raises(backup_service.BackupError):
            backup_service._validated_backup_dir(bad_name)


def test_validated_backup_dir_rejects_missing_backup():
    backup_service.BACKUP_DIR.mkdir(parents=True)
    with pytest.raises(backup_service.BackupError):
        backup_service._validated_backup_dir("20260101_120000")


def test_backup_zip_bytes_bundles_both_files():
    _make_backup_dir("20260101_130000")
    zip_bytes = backup_service.backup_zip_bytes("20260101_130000")

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    assert set(zf.namelist()) == {"database.sql", "uploads.tar.gz"}


def test_backup_zip_bytes_without_uploads_still_works():
    _make_backup_dir("20260101_140000", with_uploads=False)
    zip_bytes = backup_service.backup_zip_bytes("20260101_140000")

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    assert zf.namelist() == ["database.sql"]


def test_save_uploaded_backup_requires_database_sql():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("uploads.tar.gz", b"lo que sea")
    with pytest.raises(backup_service.BackupError):
        backup_service.save_uploaded_backup(buf.getvalue())


def test_save_uploaded_backup_rejects_bad_zip():
    with pytest.raises(backup_service.BackupError):
        backup_service.save_uploaded_backup(b"esto no es un zip")


def test_save_uploaded_backup_roundtrip_and_lands_in_list():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("database.sql", "-- dump subido\n")
        zf.writestr("uploads.tar.gz", b"contenido comprimido falso")

    info = backup_service.save_uploaded_backup(buf.getvalue())
    assert info.name.endswith("_subido")
    assert (backup_service.BACKUP_DIR / info.name / "database.sql").exists()
    assert (backup_service.BACKUP_DIR / info.name / "uploads.tar.gz").exists()

    listed = backup_service.list_backups()
    assert any(b.name == info.name for b in listed)
