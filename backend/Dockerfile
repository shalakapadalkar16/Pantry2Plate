# Single stage on purpose.
#
# The usual argument for multi-stage is keeping compilers out of the final
# image, but psycopg2-binary ships wheels and nothing else here needs a
# build toolchain. A second stage would add complexity for no size saving.
FROM python:3.12-slim

# PYTHONUNBUFFERED matters in containers: without it Python buffers stdout
# and `docker compose logs` shows nothing until the buffer flushes, which
# makes a crash look like a hang.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq5 is the runtime Postgres client library. curl is for the container
# healthcheck. Neither is a build dependency, so no toolchain is installed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Requirements copied alone and installed first, so the layer cache is only
# invalidated when dependencies change rather than on every code edit.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Non-root. A container process that does not need to write to the image
# should not be able to.
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/staticfiles \
    && chown -R app:app /app
USER app

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

# Two workers, two threads. This is a demo on one machine, not a
# deployment - the point is that gunicorn is serving rather than
# runserver, not that the worker count is tuned.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]