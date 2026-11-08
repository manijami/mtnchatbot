"""Runs the proxy/metrics API (internal) and the feed (its own port) in one process."""

import asyncio
import logging

import uvicorn

from .app import build_app
from .config import load_settings
from .feed import build_feed_app
from .ledger import Ledger


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    ledger = Ledger(settings.prices, settings.model_tiers)
    servers = [
        uvicorn.Server(uvicorn.Config(build_app(settings, ledger), host="0.0.0.0", port=settings.api_port,
                                      access_log=False, log_level="info")),
        uvicorn.Server(uvicorn.Config(build_feed_app(ledger), host="0.0.0.0", port=settings.feed_port,
                                      access_log=False, log_level="info")),
    ]
    await asyncio.gather(*(server.serve() for server in servers))


if __name__ == "__main__":
    asyncio.run(main())
