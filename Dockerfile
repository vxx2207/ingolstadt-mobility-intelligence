# Reproducible image: pinned base, JDK for the Java data-quality engine.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    INGOMOB_LOG_LEVEL=INFO

RUN apt-get update \
 && apt-get install -y --no-install-recommends default-jdk-headless make \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-dev.txt constraints.txt ./
RUN pip install -r requirements-dev.txt -c constraints.txt

COPY . .
RUN pip install --no-deps -e .

# Non-root by default.
RUN useradd --create-home --uid 10001 ingomob && chown -R ingomob /app
USER ingomob

HEALTHCHECK --interval=30s --timeout=10s CMD python -m ingomob.cli doctor || exit 1
ENTRYPOINT ["python", "-m", "ingomob.cli"]
CMD ["run-all"]
