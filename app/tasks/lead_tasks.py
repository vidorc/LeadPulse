from app.core.celery_app import celery


@celery.task(name="app.tasks.test_task")
def test_task(name: str):
    return f"Lead task executed for {name}"