# MTN branding layer on top of the UNCHANGED upstream LibreChat image (no source edits).
#
# Adds to the built client in /app/client/dist:
#   - brand assets: logo.svg, favicons, app icons, PWA manifest
#   - MTN Brighter Sans font files + mtn-fonts.css, linked from index.html
#   - <title> set to the app title (the static shell otherwise says "LibreChat")
#   - css/mtn-overrides.css: tiny layout fixes for upstream issues (always linked)
#   - design-asset slots (avatars, file-type icons, UI icons, illustrations, logo variants) under
#     /assets/mtn/<slot>/, plus /assets/mtn/assets.json listing which ones are official.
#     Slot names, formats and fallbacks: mtn/branding/ASSETS.md.
#
# Licensed/official assets come from mtn/branding/private/ (gitignored). When that
# folder is absent (fresh clone), the tracked placeholders are used and no font is added.
#
# Build (from repo root):  docker compose build api
# Rebuild whenever the base image is updated (`docker compose pull` then build).
# Upstream LibreChat built from our base commit f4154b649 (pinned by digest; see CLAUDE.md
# "Upgrading the upstream base").
ARG BASE_IMAGE=registry.librechat.ai/librechat-ai/librechat-dev@sha256:9625652b9d9ac9fbf9ff3505fc34770f822c7aa079f58d06b4e66eed2dc93aeb
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
      fv=$(sha256sum "$D/assets/fonts/mtn-fonts.css" | cut -c1-12); \
      sed -i "s#</head>#  <link rel=\"stylesheet\" href=\"assets/fonts/mtn-fonts.css?v=$fv\" />\n  </head>#" "$D/index.html"; \
      echo "branding: MTN Brighter Sans added"; \
    else echo "branding: no font files, theme falls back to Inter"; fi; \
    mkdir -p "$D/assets/mtn"; \
    : "Design-asset slots: private/<dir>/<name>.svg, else .png (wrapped in an SVG so the URL is"; \
    : "stable), else the tracked fallback assets/<dir>/<name>.svg, else nothing."; \
    official=""; \
    slot() { dir="$1"; name="$2"; out="$D/assets/mtn/$dir/$name.svg"; mkdir -p "$D/assets/mtn/$dir"; \
      if [ -f "$B/private/$dir/$name.svg" ]; then cp "$B/private/$dir/$name.svg" "$out"; official="$official \"$dir/$name\","; \
      elif [ -f "$B/private/$dir/$name.png" ]; then \
        printf '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><image width="256" height="256" href="data:image/png;base64,%s"/></svg>' \
          "$(base64 "$B/private/$dir/$name.png" | tr -d '\n')" > "$out"; official="$official \"$dir/$name\","; \
      elif [ -f "$B/assets/$dir/$name.svg" ]; then cp "$B/assets/$dir/$name.svg" "$out"; \
      fi; }; \
    for n in smart-chat document-assistant; do slot avatars "$n"; done; \
    for n in docx pptx xlsx pdf; do slot file-types "$n"; done; \
    for n in chats projects assistants files search new-chat help attach mic send share more download preview expand close; do slot icons "$n"; done; \
    for n in empty-state; do slot illustrations "$n"; done; \
    for n in logo logo-on-dark; do slot logo "$n"; done; \
    printf '{"official": [%s]}\n' "$(echo "$official" | sed 's/,$//')" > "$D/assets/mtn/assets.json"; \
    echo "branding: official design assets:${official:- none (fallbacks only)}"; \
    cp "$B/css/mtn-overrides.css" "$D/assets/mtn/mtn-overrides.css"; \
    v=$(sha256sum "$D/assets/mtn/mtn-overrides.css" | cut -c1-12); \
    : "Content hash in the URL so browsers and the PWA cache pick up every change."; \
    sed -i "s#</head>#  <link rel=\"stylesheet\" href=\"assets/mtn/mtn-overrides.css?v=$v\" />\n  </head>#" "$D/index.html"; \
    sed -i "s#<title>[^<]*</title>#<title>${APP_TITLE}</title>#" "$D/index.html"; \
    rm -f "$D/index.html.br" "$D/index.html.gz" "$D/manifest.webmanifest.br" "$D/manifest.webmanifest.gz"; \
    grep -c 'mtn-fonts.css' "$D/index.html" || true
