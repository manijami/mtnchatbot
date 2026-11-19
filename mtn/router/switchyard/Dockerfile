# NVIDIA NeMo Switchyard server (Apache-2.0) for the MTN model router demo. DEV/DEMO ONLY:
# upstream supports the standalone server for demos and local evaluation, not production.
#
# Builds switchyard-server from a pinned commit (v0.3.0) plus MTN's local patch, which makes
# llm_classifier custom mode record the judge's verdict and return it in the
# x-switchyard-route-evidence response header (docs/mtn/upstream-proposal-switchyard-reason.md).
# Base images are pinned by digest; Cargo builds with --locked against the pinned Cargo.lock.
#
#   docker build -t mtn-switchyard:0.3.0-mtn1 mtn/router/switchyard
#   docker build --target test mtn/router/switchyard     # runs the patch's unit tests

ARG SWITCHYARD_COMMIT=336196f6fbfc97ddc71c1700f6092e564e9f23c2

FROM rust:1.96.1-bookworm@sha256:a339861ae23e9abb272cea45dfafde21760d2ce6577a70f8a926153677902663 AS source
ARG SWITCHYARD_COMMIT
WORKDIR /opt/switchyard
RUN git init -q . \
 && git remote add origin https://github.com/NVIDIA-NeMo/Switchyard.git \
 && git fetch -q --depth 1 origin "${SWITCHYARD_COMMIT}" \
 && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "${SWITCHYARD_COMMIT}"
COPY patches/ /tmp/patches/
RUN for p in /tmp/patches/*.patch; do git apply --verbose "$p"; done

FROM source AS test
RUN cargo test --locked -p switchyard-libsy --lib custom_evidence_tests \
 && cargo test --locked -p switchyard-server --lib route_evidence_header_tests

FROM source AS builder
RUN cargo build --locked --release -p switchyard-server \
 && strip target/release/switchyard-server

FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc AS runtime
RUN apt-get update \
 && apt-get install --no-install-recommends -y ca-certificates=20250419~deb12u2 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/switchyard/target/release/switchyard-server /usr/local/bin/switchyard-server
COPY routes.toml /etc/switchyard/routes.toml
# Routing log directory (a named volume inherits this ownership on first use).
RUN mkdir -p /var/log/switchyard && chown 1000:1000 /var/log/switchyard
ENV HOME=/tmp
USER 1000:1000
EXPOSE 4000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["/bin/bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/4000 && printf 'GET /health HTTP/1.0\\r\\n\\r\\n' >&3 && grep -q '200' <&3"]
ENTRYPOINT ["switchyard-server"]
CMD ["--config", "/etc/switchyard/routes.toml", "--host", "0.0.0.0", "--port", "4000", "--routing-log-file", "/var/log/switchyard/routing.jsonl"]
