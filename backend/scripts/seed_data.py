"""
Script de datos de prueba — crea los usuarios base documentados en CLAUDE.md.
Ejecutar con: make seed (equivale a `cd backend && python scripts/seed_data.py`)
"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, create_tables
from app.core.security import hash_password
from app.models.user import User, UserRole

# RUTs ficticios (pero válidos, con dígito verificador real) para los
# usuarios de prueba — el RUT es ahora el identificador único de login
# (ver app/core/rut.py), así que cada cuenta necesita uno.
SEED_USERS = [
    {"email": "admin@panol.com", "rut": "1-9", "full_name": "Administrador", "role": UserRole.jefe, "password": "Admin123!"},
    {"email": "encargado@panol.com", "rut": "2-7", "full_name": "Encargado de Pañol", "role": UserRole.encargado, "password": "Admin123!"},
    {"email": "mecanico@panol.com", "rut": "3-5", "full_name": "Mecánico", "role": UserRole.mecanico, "password": "Admin123!"},
]


async def seed() -> None:
    await create_tables()
    async with AsyncSessionLocal() as db:
        for data in SEED_USERS:
            existing = await db.execute(select(User).where(User.email == data["email"]))
            if existing.scalar_one_or_none():
                print(f"⏭  {data['email']} ya existe, se omite")
                continue

            user = User(
                email=data["email"],
                rut=data["rut"],
                full_name=data["full_name"],
                role=data["role"],
                hashed_password=hash_password(data["password"]),
            )
            db.add(user)
            print(f"✅ Usuario creado: {data['email']} (RUT {data['rut']}, {data['role'].value})")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
    print("\n🌱 Datos de prueba cargados correctamente.")
