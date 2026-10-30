import os
from datetime import timedelta

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

app.conf.beat_schedule = {
    "update-last-price-every-5-min": {
        "task": "dashboard.tasks.update_last_price",
        "schedule": timedelta(minutes=5),
    },
}
