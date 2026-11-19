# MTN core-deviation overlay (local dev).
#
# The upstream image is built from the same commit as our base (f4154b649). This layer replaces
# only the backend build output of the MTN core deviations (see CLAUDE.md decisions log):
#   - packages/data-provider/dist  (configSchema: mcpServers.*.fileOutputs, FileContext.mcp_output)
#   - packages/api/dist            (MCP file outputs: policy, extraction, persistence)
#   - api/ wiring files            (tool-end callbacks, Files/process deps)
# Build the dists on the host first: npm run build:data-provider && npm run build:api
# Production builds the whole image from source in CI (repo Dockerfile) instead of this overlay.
ARG BASE_IMAGE=mtn-librechat:local
FROM ${BASE_IMAGE}
# Upstream commit the overlay was built against. Upstream images carry no commit label, so the
# check compares the image's own sources with the fingerprint of that commit
# (mtn/deploy/base-fingerprint.sha256, from mtn/scripts/base-fingerprint.sh) plus the package
# version. Any other upstream build fails here, before the overlay is copied in.
ARG BASE_COMMIT=f4154b649efa37e1345ccc517a4d8d1ed2178c82
ARG BASE_VERSION=v0.8.9-rc1
USER root
RUN --mount=type=bind,source=mtn/deploy/base-fingerprint.sha256,target=/tmp/base-fingerprint.sha256 \
    set -eu; cd /app; \
    version="$(node -p "require('/app/package.json').version")"; \
    if [ "$version" != "$BASE_VERSION" ]; then \
      echo "core overlay: base image is LibreChat $version, expected $BASE_VERSION ($BASE_COMMIT)" >&2; exit 1; \
    fi; \
    if ! sha256sum -c -s /tmp/base-fingerprint.sha256; then \
      echo "core overlay: base image sources do not match upstream commit $BASE_COMMIT." >&2; \
      echo "Rebuild the overlay against a new base only by following CLAUDE.md 'Upgrading the upstream base'." >&2; \
      exit 1; \
    fi; \
    echo "core overlay: base verified as $BASE_VERSION @ $BASE_COMMIT ($(wc -l < /tmp/base-fingerprint.sha256) files)"
RUN rm -rf /app/packages/data-provider/dist /app/packages/api/dist
COPY --chown=node:node packages/data-provider/dist /app/packages/data-provider/dist
COPY --chown=node:node packages/api/dist /app/packages/api/dist
COPY --chown=node:node api/server/controllers/agents/callbacks.js /app/api/server/controllers/agents/callbacks.js
COPY --chown=node:node api/server/services/Files/process.js /app/api/server/services/Files/process.js
USER node
