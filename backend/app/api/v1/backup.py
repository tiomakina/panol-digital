"""
API de Respaldo integral del sistema — generar, listar, descargar y
restaurar backups de la base de datos + archivos subidos.
Endpoint: /api/v1/backup/

Todo requiere rol Jefe: es infraestructura sensible (la base completa) y
restaurar es una operación destructiva por diseño.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.security import require_role, verify_password
from app.models.user import User
from app.schemas.backup import BackupOut, RestoreInput
from app.services import backup_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/backup", tags=["Respaldo"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_out(info: backup_service.BackupInfo) -> BackupOut:
    return BackupOut(
        name=info.name, created_at=info.created_at,
        database_size=info.database_size, uploads_size=info.uploads_size,
    )


@router.get("", response_model=list[BackupOut])
async def list_backups(user: User = Depends(require_role("jefe"))):
    return [_to_out(b) for b in backup_service.list_backups()]


@router.post("", response_model=BackupOut)
async def create_backup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("jefe")),
):
    """Genera un backup nuevo ahora mismo (puede tardar según el tamaño de la base)."""
    try:
        info = await backup_service.create_backup()
    except backup_service.BackupError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    await log_action(
        db, user_id=user.id, action="backup.create", entity_type="backup",
        detail=f"Backup generado: {info.name}", ip_address=_client_ip(request),
    )
    await db.commit()
    return _to_out(info)


@router.get("/{name}/download")
async def download_backup(name: str, user: User = Depends(require_role("jefe"))):
    try:
        content = backup_service.backup_zip_bytes(name)
    except backup_service.BackupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="panol_backup_{name}.zip"'},
    )


@router.post("/upload", response_model=BackupOut)
async def upload_backup(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("jefe")),
):
    """
    Sube un .zip de backup generado por este mismo módulo (por ejemplo
    bajado de otro servidor) y lo deja listo para restaurar — no lo
    restaura solo, eso es un paso aparte con POST /backup/{name}/restore.
    """
    file_bytes = await file.read()
    try:
        info = backup_service.save_uploaded_backup(file_bytes)
    except backup_service.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await log_action(
        db, user_id=user.id, action="backup.upload", entity_type="backup",
        detail=f"Backup subido: {info.name}", ip_address=_client_ip(request),
    )
    await db.commit()
    return _to_out(info)


@router.post("/{name}/restore")
async def restore_backup(
    name: str,
    payload: RestoreInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("jefe")),
):
    """
    Restaura un backup — SOBREESCRIBE la base de datos actual y los
    archivos subidos con lo que había en ese momento. Pide la contraseña
    del Jefe como confirmación extra, igual que desactivar el 2FA.

    El restore mata todas las conexiones activas contra la base (incluida
    la de este mismo request) para poder tomar los locks que necesita.
    Por eso cerramos `db` nosotros mismos ANTES de restaurar — así, cuando
    FastAPI intente hacer su commit() automático de limpieza al terminar
    el request, la sesión ya se dio cuenta que no tiene nada pendiente
    (abre una conexión nueva sola si hace falta) en vez de reventar contra
    la conexión vieja, que para ese momento ya está cortada del lado del
    servidor. El asiento de auditoría se escribe aparte, con una conexión
    nueva, recién cuando el restore ya terminó.
    """
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña es incorrecta")

    await db.close()
    try:
        await backup_service.restore_backup(name)
    except backup_service.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    async with AsyncSessionLocal() as fresh_db:
        await log_action(
            fresh_db, user_id=user.id, action="backup.restore", entity_type="backup",
            detail=f"Sistema restaurado desde el backup: {name}", ip_address=_client_ip(request),
        )
        await fresh_db.commit()
    return {"success": True, "message": f"Sistema restaurado desde {name}"}
