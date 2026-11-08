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
USER root
RUN rm -rf /app/packages/data-provider/dist /app/packages/api/dist
COPY --chown=node:node packages/data-provider/dist /app/packages/data-provider/dist
COPY --chown=node:node packages/api/dist /app/packages/api/dist
COPY --chown=node:node api/server/controllers/agents/callbacks.js /app/api/server/controllers/agents/callbacks.js
COPY --chown=node:node api/server/services/Files/process.js /app/api/server/services/Files/process.js
USER node
