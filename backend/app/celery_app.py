"""
Configuración de Celery — tareas asíncronas en segundo plano.
Arrancado por el contenedor `celery_worker` (y `celery_beat` para las
tareas periódicas) definidos en docker-compose.yml.
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery("panol", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "marcar-prestamos-vencidos": {
            "task": "app.tasks.loan_tasks.mark_overdue_loans",
            "schedule": crontab(minute=0),  # cada hora, en punto
        },
    },
)

# Import directo (en vez de autodiscover_tasks) para que las tareas queden
# registradas de forma explícita y predecible.
from app.tasks import loan_tasks  # noqa: E402,F401
