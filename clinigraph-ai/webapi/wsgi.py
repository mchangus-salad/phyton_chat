"""
WSGI config for webapi project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webapi.settings')

# Initialise OpenTelemetry tracing before the first request is handled.
from api.tracing import setup_tracing  # noqa: E402  (must come after settings is set)
setup_tracing()

application = get_wsgi_application()
