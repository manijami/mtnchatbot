# MTN office-mcp — template-driven Office document generation (Phase 4).
# Pinned base image digest + pinned Debian package versions + hash-locked Python wheels.
# Nothing is installed at runtime. If a pinned Debian version leaves the mirror, rebuild from
# snapshot.debian.org at the same date rather than unpinning.
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libreoffice-writer-nogui=4:7.4.7-1+deb12u14 \
      libreoffice-calc-nogui=4:7.4.7-1+deb12u14 \
      libreoffice-impress-nogui=4:7.4.7-1+deb12u14 \
      poppler-utils=22.12.0-2+deb12u3 \
      fonts-liberation=1:1.07.4-11 \
      fontconfig=2.14.1-4 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 office \
 && useradd --system --uid 10001 --gid office --home-dir /home/office --create-home office

# "MTN Brighter Sans" renders as Arial-metric Liberation Sans in previews (no font is embedded).
COPY fontconfig/60-mtn-fonts.conf /etc/fonts/conf.d/60-mtn-fonts.conf
RUN fc-cache -f >/dev/null

WORKDIR /app
COPY requirements.lock .
RUN pip install --require-hashes --no-deps -r requirements.lock

COPY office_mcp ./office_mcp
RUN mkdir -p /data /app/templates /app/brand/logo && chown office:office /data

FROM base AS test
COPY requirements-dev.lock .
RUN pip install --require-hashes --no-deps -r requirements-dev.lock
COPY tests ./tests
USER office
ENV HOME=/home/office OFFICE_MCP_DATA_DIR=/tmp/office-test-data
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]

FROM base AS runtime
USER office
ENV HOME=/home/office
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
CMD ["python", "-m", "office_mcp"]
