import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECURE_MODE = os.environ.get("SECURE", "0") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-secret")
if SECURE_MODE and SECRET_KEY == "dev-only-not-secret":
    raise ImproperlyConfigured("SECURE=1 requires a real SECRET_KEY")

BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "")
BASIC_AUTH_PASSWORD = os.environ.get("BASIC_AUTH_PASSWORD", "")
BASIC_AUTH_REALM = os.environ.get("BASIC_AUTH_REALM", "LCD to FBMDR")
if bool(BASIC_AUTH_USER) != bool(BASIC_AUTH_PASSWORD):
    raise ImproperlyConfigured(
        "Set both BASIC_AUTH_USER and BASIC_AUTH_PASSWORD, or neither."
    )
DEBUG = os.environ.get("DEBUG", "0" if SECURE_MODE else "1") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "*").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# Basic hardening is safe in development too. Transport security is opt-in so
# the HTTP dev server keeps working; set SECURE=1 behind TLS.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_SSL_REDIRECT = SECURE_MODE
SESSION_COOKIE_SECURE = SECURE_MODE
CSRF_COOKIE_SECURE = SECURE_MODE
SECURE_HSTS_SECONDS = 31536000 if SECURE_MODE else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_MODE
SECURE_HSTS_PRELOAD = SECURE_MODE
if SECURE_MODE and os.environ.get("TRUST_PROXY") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "review",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "review.middleware.BasicAuthMiddleware",
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "55433"),
        "NAME": os.environ.get("DB_NAME", "mdr"),
        "USER": os.environ.get("DB_USER", "mdr"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "mdr"),
        "OPTIONS": {
            # prefer negotiates TLS when the server offers it and falls back for
            # local development. Docker Compose sets require explicitly.
            "sslmode": os.environ.get("DB_SSLMODE", "prefer"),
            "connect_timeout": 5,
            "application_name": "mdr-reuse",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
