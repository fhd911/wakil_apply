from pathlib import Path
import os

# =========================
# Paths
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent

# =========================
# .env loader (بدون مكتبات إضافية)
# =========================
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# =========================
# Security
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

# في Render اجعلها 0
DEBUG = os.getenv("DEBUG", "0") == "1"

# ALLOWED_HOSTS:
# - يمكن ضبطها يدويًا من Render
# - وإذا لم تضبطها، نستخدم دومين Render تلقائيًا إن وجد
render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
allowed_hosts_env = os.getenv("ALLOWED_HOSTS", "")

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)

if allowed_hosts_env:
    ALLOWED_HOSTS += [h.strip() for h in allowed_hosts_env.split(",") if h.strip()]
else:
    ALLOWED_HOSTS.append("*")

ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))  # إزالة التكرار

# إذا كنت تستخدم دومين HTTPS على Render
CSRF_TRUSTED_ORIGINS = []
if render_hostname:
    CSRF_TRUSTED_ORIGINS.append(f"https://{render_hostname}")

csrf_env = os.getenv("CSRF_TRUSTED_ORIGINS", "")
if csrf_env:
    CSRF_TRUSTED_ORIGINS += [u.strip() for u in csrf_env.split(",") if u.strip()]

CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

# =========================
# Apps
# =========================
INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",  # يساعد محليًا مع WhiteNoise

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # مشروعنا
    "portal",
]

# =========================
# Middleware
# =========================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # ملفات static على Render

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# =========================
# URLs / WSGI
# =========================
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# =========================
# Templates
# =========================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

# =========================
# Database
# - PostgreSQL من DATABASE_URL إذا كانت موجودة
# - وإلا يرجع إلى SQLite
# =========================
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # يحتاج psycopg2-binary في requirements.txt
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    from urllib.parse import urlparse

    db = urlparse(DATABASE_URL)

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db.path[1:],
            "USER": db.username,
            "PASSWORD": db.password,
            "HOST": db.hostname,
            "PORT": db.port or 5432,
            "CONN_MAX_AGE": 600,
            "OPTIONS": {
                "sslmode": "require",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# =========================
# Password validation
# =========================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =========================
# i18n / l10n
# =========================
LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

# =========================
# Static / Media
# =========================
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =========================
# Default PK
# =========================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =========================
# Sessions
# =========================
SESSION_COOKIE_AGE = 60 * 60 * 6  # 6 ساعات
SESSION_SAVE_EVERY_REQUEST = True

# =========================
# Security headers للإنتاج
# =========================
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"