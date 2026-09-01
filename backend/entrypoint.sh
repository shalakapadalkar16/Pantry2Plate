#!/usr/bin/env bash
#
# Wait for Postgres, then migrate and collect static before handing over to
# whatever CMD was given.
#
# Compose already has `depends_on: service_healthy`, so this is belt and
# braces - but a healthy Postgres container and a Postgres accepting
# connections are not quite the same instant, and the failure mode without
# the wait is a crash loop that looks like a bad DATABASE_URL.
#
# Caveat worth knowing: running migrate on start does not survive
# horizontal scaling. Two containers booting together would both attempt
# it. Django wraps migrations in a transaction so the loser fails rather
# than corrupting anything, but in a real deployment this belongs in a
# release step, not in the app entrypoint.
set -e

python <<'PYTHON'
import os
import sys
import time
import urllib.parse

url = os.environ.get("DATABASE_URL", "")
parsed = urllib.parse.urlparse(url)
host = parsed.hostname or "db"
port = parsed.port or 5432

import socket

deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"postgres reachable at {host}:{port}")
            sys.exit(0)
    except OSError:
        time.sleep(1)

print(f"postgres unreachable at {host}:{port} after 60s", file=sys.stderr)
sys.exit(1)
PYTHON

echo "running migrations"
python manage.py migrate --noinput

echo "loading ingredient vocabulary"
python manage.py load_ingredients

echo "collecting static files"
python manage.py collectstatic --noinput --clear

exec "$@"