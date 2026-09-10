# Multi-stage: dependencies resolved once, runtime image carries no build tools.
FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml ./
COPY dgate ./dgate
RUN python -m venv /opt/venv && /opt/venv/bin/pip install .

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# postgresql-client is here for one reason: the worker takes the nightly dump,
# and a backup tool that lives on somebody's laptop is not a backup tool.
RUN apt-get update  && apt-get install -y --no-install-recommends postgresql-client  && rm -rf /var/lib/apt/lists/*

# Non-root. The container reads public data and writes to a mounted volume; it
# has no business running as root.
RUN useradd --create-home --uid 10001 dgate

COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=dgate:dgate dgate ./dgate
COPY --chown=dgate:dgate migrations ./migrations

# Create the mount points in the image and give them to the non-root user.
# A named volume inherits the ownership of the image path it covers; without
# this the first write fails with EACCES, which is a fine thing to discover
# now and a terrible thing to discover on the first night of ingestion.
# Every path that gets a named volume mounted over it needs to exist and be
# owned here. Docker creates a missing mount point as root, and the container
# does not run as root, so the first write fails with EACCES -- which is how
# /raw, /backups and now /data/atlas each found out in turn.
RUN mkdir -p /raw /backups /data/atlas  && chown dgate:dgate /raw /backups /data/atlas

USER dgate

# Overridden per service in docker-compose.yml.
CMD ["uvicorn", "dgate.api:app", "--host", "0.0.0.0", "--port", "8000"]
