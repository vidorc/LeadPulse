from celery import Celery
from app.core.config import settings


celery = Celery(
    "leadpulse",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.lead_tasks"
    ]
)