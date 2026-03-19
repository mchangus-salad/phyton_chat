"""Django settings for webapi project."""

import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.agentai.local")
load_dotenv(BASE_DIR / ".env")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'unsafe-dev-secret-change-in-prod')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DJANGO_DEBUG', 'true').lower() == 'true'

ALLOWED_HOSTS = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'api.middleware.RequestIDMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'webapi.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'webapi.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DJANGO_DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.getenv('DJANGO_DB_NAME', str(BASE_DIR / 'db.sqlite3')),
        'USER': os.getenv('DJANGO_DB_USER', ''),
        'PASSWORD': os.getenv('DJANGO_DB_PASSWORD', ''),
        'HOST': os.getenv('DJANGO_DB_HOST', ''),
        'PORT': os.getenv('DJANGO_DB_PORT', ''),
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'

SECURE_SSL_REDIRECT = os.getenv('DJANGO_SECURE_SSL_REDIRECT', 'false').lower() == 'true'
SESSION_COOKIE_SECURE = os.getenv('DJANGO_SESSION_COOKIE_SECURE', 'false').lower() == 'true'
CSRF_COOKIE_SECURE = os.getenv('DJANGO_CSRF_COOKIE_SECURE', 'false').lower() == 'true'
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'false').lower() == 'true'
SECURE_HSTS_PRELOAD = os.getenv('DJANGO_SECURE_HSTS_PRELOAD', 'false').lower() == 'true'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

AGENT_API_KEY = os.getenv('AGENT_API_KEY', '')

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('DRF_THROTTLE_ANON', '120/min'),
        'user': os.getenv('DRF_THROTTLE_USER', '300/min'),
        'agent_anon': os.getenv('DRF_THROTTLE_AGENT_ANON', '30/min'),
        'agent_user': os.getenv('DRF_THROTTLE_AGENT_USER', '120/min'),
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Chat Build Agent API',
    'DESCRIPTION': 'AgentAI endpoints with JWT Bearer and API key authentication options.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'PREPROCESSING_HOOKS': [
        'webapi.schema.exclude_legacy_api_paths',
    ],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            },
            'ApiKeyAuth': {
                'type': 'apiKey',
                'in': 'header',
                'name': 'X-API-Key',
            },
        },
    },
    'SECURITY': [
        {'BearerAuth': []},
        {'ApiKeyAuth': []},
    ],
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_MINUTES', '30'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '7'))),
    'ROTATE_REFRESH_TOKENS': os.getenv('JWT_ROTATE_REFRESH_TOKENS', 'false').lower() == 'true',
    'BLACKLIST_AFTER_ROTATION': os.getenv('JWT_BLACKLIST_AFTER_ROTATION', 'false').lower() == 'true',
}

LOG_LEVEL = os.getenv('DJANGO_LOG_LEVEL', 'INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
        },
        'api': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    },
}
