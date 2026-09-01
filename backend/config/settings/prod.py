from decouple import config

from .base import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS = [h for h in config("DJANGO_ALLOWED_HOSTS", default="").split(",") if h]

CORS_ALLOWED_ORIGINS = [
    o for o in config("CORS_ALLOWED_ORIGINS", default="").split(",") if o
]

# Every TLS setting is environment-gated rather than hardcoded on.
#
# These were unconditionally True, which is correct for a public deployment
# and wrong everywhere else: running prod settings over plain HTTP with
# SECURE_SSL_REDIRECT on produces an infinite redirect loop, and secure
# cookies are never sent so login silently fails. Gating them means one
# settings module works both behind TLS and in a local container.
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)

# HSTS is deliberately tied to the same switch. Sending it over HTTP is
# meaningless, and sending it from a local instance would pin the browser
# to HTTPS for localhost - which then breaks every other local project on
# the same host for a year.
if SECURE_SSL_REDIRECT:
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Behind a proxy, Django cannot see the original scheme without being told.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cheap headers with no configuration cost.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"