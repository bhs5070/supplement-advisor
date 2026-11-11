"""At-least-once delivery; DB claims provide idempotency and recovery."""

from celery import Celery

from .config import configure_logging, get_settings

configure_logging()
settings = get_settings()
celery_app = Celery(
    "supplement_advisor", broker=settings.redis_url, include=["supplement_advisor.tasks"]
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 300},
    broker_connection_timeout=3,
    task_publish_retry=False,
    task_soft_time_limit=70,
    task_time_limit=80,
    task_annotations={
        "supplement_advisor.process_analysis": {
            "soft_time_limit": min(settings.attempt_timeout_seconds, settings.analysis_timeout_seconds) - 1,
            "time_limit": min(settings.attempt_timeout_seconds, settings.analysis_timeout_seconds),
        }
    },
    beat_schedule={
        "recover-persisted-requests": {
            "task": "supplement_advisor.recover_pending",
            "schedule": 15.0,
        }
    },
)
