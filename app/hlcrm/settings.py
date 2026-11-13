"""
Settings for the CRM (H & L Roofers' and any other business's).

Anything that differs between your PC and the server (secret key, database,
web address) is read from a file named ".env" next to manage.py. Copy
".env.example" to ".env" and edit it. The .env file is never put in git.
"""
import os
import sys
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------- read the .env file ----------
def _load_env(path):
    """Read KEY=value lines from the .env file into the environment (existing values win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")


def env(key, default=""):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return env(key, str(default)).lower() in ("1", "true", "yes", "on")


# ---------- the basics ----------
DEBUG = env_bool("DEBUG", False)          # True on your PC, False on the server
SECRET_KEY = env("SECRET_KEY") or ("dev-only-key-not-for-the-server" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("Set SECRET_KEY in the .env file (see .env.example).")

# Web addresses this app answers to, separated by commas. On the server: app.handlroofers.com
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",      # lets Search find close spellings when the database is PostgreSQL
    "crm",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",         # English or Spanish, per person
    "django.middleware.common.CommonMiddleware",
    "crm.inline.SectionMiddleware",                      # which section of a record is being edited in place (inline.py)
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if not DEBUG:
    # On the server, WhiteNoise hands out the CSS and JavaScript files. (On your PC, "runserver" does that itself.)
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "hlcrm.urls"
WSGI_APPLICATION = "hlcrm.wsgi.application"

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
                "crm.context.navigation",
                "crm.context.company",
            ],
        },
    },
]

# ---------- database ----------
# With no DB_NAME in .env, the app uses a single file (db.sqlite3) so it runs on your PC with nothing
# else installed. On the server, set the DB_ lines in .env and it uses PostgreSQL.
if env("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER", "hlcrm"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- people and sign-in ----------
AUTH_USER_MODEL = "crm.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "start"                    # the dashboard, Today or My Day, by profile
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30          # stay signed in for 30 days, so nobody types a password on a roof
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# ---------- language, dates and time ----------
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("es", "Español")]
LOCALE_PATHS = [BASE_DIR / "crm" / "locale"]
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365        # the EN / ES choice is remembered on that phone or computer for a year
TIME_ZONE = env("TIME_ZONE", "America/New_York")    # where the business is (H & L: Virginia)
USE_I18N = True
USE_TZ = True

# ---------- CSS, JavaScript and images ----------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"          # filled by: python manage.py collectstatic (server only)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
                    else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------- safer cookies when the app is on the real web address ----------
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")      # Cloudflare Tunnel passes this along

# ---------- email: proposals, invoices and summaries ----------
# With no EMAIL_HOST in .env the app cannot send email. On your PC it then writes each email to the
# server window instead, so you can read what would have been sent.
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = env("EMAIL_FROM", EMAIL_HOST_USER or "office@example.com")
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend"
EMAIL_READY = bool(EMAIL_HOST) or DEBUG          # False on a server with no email set up: the Email buttons explain why

# The address customers see in emailed links (the Accept page). On the server: https://app.handlroofers.com
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000").rstrip("/")

# ---------- the website's request form ----------
# The website sends each request to /leads/in/ with this key. With no key, that address is switched off.
LEAD_FORM_KEY = env("LEAD_FORM_KEY")
LEAD_FORM_ORIGIN = env("LEAD_FORM_ORIGIN", "*")  # the website's address, e.g. https://handlroofers.com

# ---------- CRM settings ----------
FIRST_JOB_NUMBER = int(env("FIRST_JOB_NUMBER", "101"))    # the first number each year: 26-101, 26-102, ...


def work_days_from(text):
    """WORK_DAYS as written in .env (mon,tue,wed,thu,fri) -> the days' numbers, 0 being Monday: [0, 1, 2, 3, 4]"""
    days = [word.strip().lower()[:3] for word in text.split(",") if word.strip()]
    if not days or any(day not in DAY_KEYS for day in days):
        raise ImproperlyConfigured("WORK_DAYS in .env: list the work days with commas, like this: mon,tue,wed,thu,fri")
    return sorted({DAY_KEYS.index(day) for day in days})


# The work days. A day off can still be booked by hand ("Work on a day off").
# H & L: Monday to Friday. Saturday is never a work day; Sunday is not decided yet.
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WORK_WEEKDAYS = work_days_from(env("WORK_DAYS", "mon,tue,wed,thu,fri"))

# ---------- where the business is (H & L's are the defaults) ----------
STATE = env("STATE", "VA").upper()                     # the state a new address starts with
STATE_NAME = env("STATE_NAME", "Virginia")             # the state's name, as notes may spell it out
# The notes import reads a ZIP code only when it starts with one of these. H & L: 20 to 24 (Virginia and around).
ZIP_STARTS = [start.strip() for start in env("ZIP_STARTS", "20,21,22,23,24").split(",") if start.strip()]
if any(not start.isdigit() or len(start) > 5 for start in ZIP_STARTS):
    raise ImproperlyConfigured("ZIP_STARTS in .env: the first digits of the business's ZIP codes, with commas, like this: 20,21,22")
# The towns the notes import knows when a note gives a town with no state or ZIP code.
# Empty: the towns around Richmond, while STATE is VA.
IMPORT_TOWNS = [town.strip() for town in env("IMPORT_TOWNS").split(",") if town.strip()]
# More words that mean a note is about the work. The import already knows roofing words, in English and Spanish.
IMPORT_WORK_WORDS = [word.strip() for word in env("IMPORT_WORK_WORDS").split(",") if word.strip()]
# Apple Notes folders that are never imported, separated by commas. Notes in them are counted, not stored.
IMPORT_SKIP_FOLDERS = [f.strip() for f in env("IMPORT_SKIP_FOLDERS", "Passwords and accounts").split(",") if f.strip()]
# The notes export holds passwords, so the uploaded file is only ever held in memory, never written to the disk.
# A file larger than this is refused.
FILE_UPLOAD_HANDLERS = ["django.core.files.uploadhandler.MemoryFileUploadHandler"]
FILE_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024        # one upload, all files together: room for a dozen phone photos

# Photos and files added to jobs and accounts. They are kept in this folder, which the backups must include, and are
# shown only through the app, to the logins that may see that job or account. On the server, set MEDIA_ROOT in .env.
MEDIA_ROOT = Path(env("MEDIA_ROOT") or BASE_DIR / "media")
MAX_FILE_SIZE = 25 * 1024 * 1024                        # one photo or file


# ---------- health: free disk space and free memory (checked by "python manage.py tick") ----------
# Below any of these, the app writes a warning in errors.log and in Admin > Setup history, and emails the administrators.
DISK_MIN_GB = float(env("DISK_MIN_GB", "10"))           # less than this many GB free on a drive the app uses
DISK_MIN_PERCENT = float(env("DISK_MIN_PERCENT", "10"))  # or less than this share of the drive free
RAM_MIN_MB = float(env("RAM_MIN_MB", "500"))            # less than this many MB of memory free

# ---------- the log files ----------
# errors.log (WARNING and up, with full tracebacks) and changes.log (every history line), in this folder. The backups
# need not include it. Admin > System status shows the end of errors.log and has a link to download each file.
LOG_DIR = Path(env("LOG_DIR") or BASE_DIR / "logs")
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
if TESTING:
    LOG_DIR = Path(tempfile.gettempdir()) / "hl-crm-test-logs"      # the tests never write into the real log folder
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass                                                    # a log folder that cannot be made must not stop the app

_LINE = "%(asctime)s %(levelname)s %(name)s %(message)s"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"line": {"format": _LINE, "datefmt": "%Y-%m-%d %H:%M:%S"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "line", "level": "WARNING"},
        "errors": {"class": "crm.logs.QuietRotatingFileHandler", "filename": str(LOG_DIR / "errors.log"), "formatter": "line", "level": "WARNING"},
        "changes": {"class": "crm.logs.QuietRotatingFileHandler", "filename": str(LOG_DIR / "changes.log"), "formatter": "line", "level": "INFO"},
    },
    # everything of WARNING and up goes to errors.log and to the console: Django's 500 errors with their tracebacks,
    # the app's own "crm" loggers, and anything else that complains
    "root": {"handlers": ["console", "errors"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": [], "level": "INFO", "propagate": True},      # Django's own console printing is replaced by the root's
        "django.request": {"level": "ERROR"},                                  # the 500 errors; a page not found or refused (404, 403) is not an error
        "crm.changes": {"handlers": ["changes"], "level": "INFO", "propagate": False},
    },
}
if TESTING:
    LOGGING["handlers"]["console"]["level"] = "CRITICAL"       # a test run stays quiet; the tests that look for log lines catch them themselves
