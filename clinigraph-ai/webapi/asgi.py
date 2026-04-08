"""
ASGI config for webapi project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webapi.settings')

# Initialise OpenTelemetry tracing before the first request is handled.
from api.tracing import setup_tracing  # noqa: E402  (must come after settings is set)
setup_tracing()

application = get_asgi_application()
