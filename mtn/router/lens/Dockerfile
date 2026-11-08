# router-lens: shows how the MTN Smart Router routed each turn. DEV/DEMO ONLY.
# Pinned base digest + hash-locked wheels; holds no provider credentials.
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN groupadd --system --gid 10002 lens && useradd --system --uid 10002 --gid lens --no-create-home lens
WORKDIR /app
COPY requirements.lock .
RUN pip install --require-hashes --no-deps -r requirements.lock
COPY prices.json ./prices.json
COPY router_lens ./router_lens

FROM base AS test
COPY requirements-dev.lock .
RUN pip install --require-hashes --no-deps -r requirements-dev.lock
COPY tests ./tests
USER lens
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]

FROM base AS runtime
USER lens
EXPOSE 8080 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"]
CMD ["python", "-m", "router_lens"]
