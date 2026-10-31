import os
import warnings
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY не задан. Укажите его в .env или в переменных окружения."
        )
    # Только для разработки: ключ меняется при каждом запуске, сессии сбрасываются.
    SECRET_KEY = get_random_secret_key()
    warnings.warn("DJANGO_SECRET_KEY не задан, сгенерирован временный ключ.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "crispy_forms",
    "crispy_bootstrap5",
    "dashboard",
    "user",
    "rest_framework",
    "django_filters",
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "main_format": {
            "format": "[{module} {asctime} {levelname}] {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "main_format"},
        "file": {
            "class": "logging.FileHandler",
            "formatter": "main_format",
            "filename": BASE_DIR / "app.logs",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "main": {"handlers": ["console", "file"], "level": "INFO", "propagate": True}
    },
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DB_ENGINE = os.getenv("DB_ENGINE", "postgresql").strip().lower()

if DB_ENGINE == "sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / os.getenv("SQLITE_PATH", "db.sqlite3"),
        }
    }
elif DB_ENGINE == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "investing"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    raise ImproperlyConfigured(
        f"Неизвестный DB_ENGINE={DB_ENGINE!r}: ожидается postgresql или sqlite3."
    )

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LOGIN_URL = "user:auth"
LOGIN_REDIRECT_URL = "dashboard:index"

LANGUAGE_CODE = "ru-ru"

TIME_ZONE = "Europe/Moscow"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

"""T-Invest API (REST-шлюз)"""
TINKOFF_TOKEN = os.getenv("TINKOFF_TOKEN", "")
TINVEST_API_URL = os.getenv(
    "TINVEST_API_URL", "https://invest-public-api.tbank.ru/rest"
).rstrip("/")
# Путь к PEM-файлу с цепочкой сертификатов (корневой УЦ Минцифры); пусто — системные
TINVEST_CA_BUNDLE = os.getenv("TINVEST_CA_BUNDLE", "")
TINVEST_TIMEOUT = float(os.getenv("TINVEST_TIMEOUT", "10"))

"""Московская биржа (ISS) — открытые данные без токена"""
MOEX_ISS_URL = os.getenv("MOEX_ISS_URL", "https://iss.moex.com/iss").rstrip("/")
# TQBR — основной режим торгов акциями
MOEX_BOARD = os.getenv("MOEX_BOARD", "TQBR")
MOEX_TIMEOUT = float(os.getenv("MOEX_TIMEOUT", "15"))

# Сколько секунд кэшировать исторические свечи для графика на карточке акции
CANDLES_CACHE_TIMEOUT = 60 * 60

"""Celery Configuration Options"""
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")

"""Debug Celery"""
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)
