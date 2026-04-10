import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webapi.settings')

app = Celery('clinigraph')

# Load CELERY_* settings from Django settings module.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all INSTALLED_APPS.
app.autodiscover_tasks()
