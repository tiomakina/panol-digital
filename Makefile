.PHONY: dev test migrate migrate-create seed seed-sample up down logs shell build-installer backup restore

# Desarrollo local
dev:
	cd backend && uvicorn app.main:app --reload --port 8000

# Tests
test:
	cd backend && pytest -v --asyncio-mode=auto

# Migraciones
migrate:
	cd backend && alembic upgrade head

migrate-create:
	cd backend && alembic revision --autogenerate -m "$(msg)"

# Datos de prueba
seed:
	cd backend && python scripts/seed_data.py

# Datos de ejemplo (herramientas, préstamos, cajas) — requiere haber corrido "seed" antes
seed-sample:
	cd backend && python scripts/seed_sample_data.py

# Docker
up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker-compose exec backend bash

# Construcción del instalador GUI
build-installer:
	bash scripts/build_installer.sh

# Backup
backup:
	bash scripts/backup.sh

# Restaurar (make restore dir=backups/20260812_120000)
restore:
	bash scripts/restore.sh $(dir)
