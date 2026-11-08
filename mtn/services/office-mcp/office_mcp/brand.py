"""MTN brand constants and the optional official logo.

Colours follow the MTN palette used by the web theme. The font is named, never embedded: Office
uses MTN Brighter Sans where installed and falls back to Arial (Word via the font table's altName).
"""

from __future__ import annotations

import io
import threading
from pathlib import Path

FONT = "MTN Brighter Sans"
FONT_FALLBACK = "Arial"

YELLOW = "FFCB05"
BLACK = "000000"
INK = "1F1F1F"  # body text
GREY_DARK = "404040"
GREY = "6B6B6B"
GREY_LIGHT = "D9D9D9"
TINT = "FFF5CC"  # light yellow tint for zebra rows / callouts
WHITE = "FFFFFF"

CLASSIFICATION = "MTN Internal"

# Preferred logo files, in order. The yellow tile reads on white pages and on black slides.
LOGO_CANDIDATES = ("yello_logo.jpg", "yellow_logo.jpg", "logo.png", "logo.jpg")
LOGO_PIXELS = 400

_logo_lock = threading.Lock()
_logo_cache: dict[Path, bytes | None] = {}


def load_logo(logo_dir: Path) -> bytes | None:
    """The official logo as a small PNG, or None when the private folder has none.

    Source files are large (8000 px), so they are downscaled once per process.
    """
    with _logo_lock:
        if logo_dir in _logo_cache:
            return _logo_cache[logo_dir]
        result = None
        for name in LOGO_CANDIDATES:
            path = logo_dir / name
            if path.is_file():
                from PIL import Image

                with Image.open(path) as image:
                    image = image.convert("RGB")
                    image.thumbnail((LOGO_PIXELS, LOGO_PIXELS))
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG", optimize=True)
                    result = buffer.getvalue()
                break
        _logo_cache[logo_dir] = result
        return result
