"""Entry point: ``python -m office_mcp``."""

import logging
import sys

import uvicorn

from .app import build_app
from .config import ConfigError, load_settings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = load_settings()
    except ConfigError as exc:
        logging.getLogger("office_mcp").error("configuration error: %s", exc)
        return 2
    uvicorn.run(
        build_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
        access_log=False,  # access logs would record document ids per user; keep them off
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
