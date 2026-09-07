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

# Non-root. The container reads public data and writes to a mounted volume; it
# has no business running as root.
RUN useradd --create-home --uid 10001 dgate

COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=dgate:dgate dgate ./dgate
COPY --chown=dgate:dgate migrations ./migrations

USER dgate

# Overridden per service in docker-compose.yml.
CMD ["uvicorn", "dgate.api:app", "--host", "0.0.0.0", "--port", "8000"]
