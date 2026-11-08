# MTN branding layer on top of the UNCHANGED upstream LibreChat image (no source edits).
#
# Adds to the built client in /app/client/dist:
#   - brand assets: logo.svg, favicons, app icons, PWA manifest
#   - MTN Brighter Sans font files + mtn-fonts.css, linked from index.html
#   - <title> set to the app title (the static shell otherwise says "LibreChat")
#   - css/mtn-overrides.css: tiny layout fixes for upstream issues (always linked)
#
# Licensed/official assets come from mtn/branding/private/ (gitignored). When that
# folder is absent (fresh clone), the tracked placeholders are used and no font is added.
#
# Build (from repo root):  docker compose build api
# Rebuild whenever the base image is updated (`docker compose pull` then build).
ARG BASE_IMAGE=registry.librechat.ai/librechat-ai/librechat-dev:latest
FROM ${BASE_IMAGE}

ARG APP_TITLE="MTN Employee AI"

# Bind-mount the build context instead of COPY so private files never land in a layer
# other than their final location.
RUN --mount=type=bind,source=.,target=/tmp/mtn-branding \
    set -eu; \
    B=/tmp/mtn-branding; D=/app/client/dist; \
    if [ -f "$B/private/generated/logo.svg" ]; then A="$B/private/generated"; echo "branding: official assets"; \
    else A="$B/assets"; echo "branding: PLACEHOLDER assets"; fi; \
    for f in logo.svg favicon-16x16.png favicon-32x32.png apple-touch-icon-180x180.png icon-192x192.png maskable-icon.png; do \
      cp "$A/$f" "$D/assets/$f"; \
    done; \
    cp "$B/manifest.webmanifest" "$D/manifest.webmanifest"; \
    if ls "$B"/private/fonts/MTNBrighterSans-*.otf >/dev/null 2>&1; then \
      mkdir -p "$D/assets/fonts"; \
      cp "$B"/private/fonts/MTNBrighterSans-*.otf "$D/assets/fonts/"; \
      cp "$B/fonts/mtn-fonts.css" "$D/assets/fonts/mtn-fonts.css"; \
      sed -i 's#</head>#  <link rel="stylesheet" href="assets/fonts/mtn-fonts.css" />\n  </head>#' "$D/index.html"; \
      echo "branding: MTN Brighter Sans added"; \
    else echo "branding: no font files, theme falls back to Inter"; fi; \
    mkdir -p "$D/assets/mtn"; \
    cp "$B/css/mtn-overrides.css" "$D/assets/mtn/mtn-overrides.css"; \
    sed -i 's#</head>#  <link rel="stylesheet" href="assets/mtn/mtn-overrides.css" />\n  </head>#' "$D/index.html"; \
    sed -i "s#<title>[^<]*</title>#<title>${APP_TITLE}</title>#" "$D/index.html"; \
    rm -f "$D/index.html.br" "$D/index.html.gz" "$D/manifest.webmanifest.br" "$D/manifest.webmanifest.gz"; \
    grep -c 'mtn-fonts.css' "$D/index.html" || true
