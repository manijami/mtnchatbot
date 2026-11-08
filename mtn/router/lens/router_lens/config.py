"""Settings from the environment. router-lens holds no provider credentials."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return default if not raw else raw in {"1", "true", "yes", "on"}


# One-sentence routing rules, shown when the judge gave no reason.
TIER_RULES = {
    "fast": "greeting, thanks or quick rewording",
    "balanced": "everyday work question",
    "capable": "multi-step analysis or careful judgement",
    "vision": "image attached",
}


@dataclass(frozen=True)
class Settings:
    switchyard_url: str = "http://switchyard:4000"
    primary_route: str = "mtn-smart"
    backup_route: str = "mtn-smart-backup-judge"
    vision_route: str | None = "mtn-smart-vision"  # None: image turns get a polite refusal
    show_footer: bool = False
    redact_prompts: bool = True
    api_port: int = 8080
    feed_port: int = 8090
    stats_poll_seconds: float = 10.0
    first_byte_timeout: float = 45.0  # seconds until the routed model must start answering
    idle_timeout: float = 45.0  # longest silence allowed once an answer is streaming
    prices: dict = field(default_factory=dict)
    model_tiers: dict = field(default_factory=dict)


def load_settings() -> Settings:
    prices_path = Path(os.environ.get("ROUTER_LENS_PRICES", Path(__file__).parent.parent / "prices.json"))
    prices = json.loads(prices_path.read_text())
    tiers = json.loads(
        os.environ.get(
            "ROUTER_LENS_MODEL_TIERS",
            '{"openai/gpt-oss-20b": "fast", "openai/gpt-oss-120b": "balanced", '
            '"nvidia/nemotron-3-ultra-550b-a55b": "capable", '
            '"nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": "vision"}',
        )
    )
    return Settings(
        switchyard_url=os.environ.get("SWITCHYARD_URL", "http://switchyard:4000").rstrip("/"),
        primary_route=os.environ.get("ROUTER_PRIMARY_ROUTE", "mtn-smart"),
        backup_route=os.environ.get("ROUTER_BACKUP_ROUTE", "mtn-smart-backup-judge"),
        vision_route=os.environ.get("ROUTER_VISION_ROUTE", "mtn-smart-vision") or None,
        show_footer=_flag("SHOW_ROUTING_FOOTER", False),
        redact_prompts=_flag("REDACT_PROMPTS", True),
        api_port=int(os.environ.get("ROUTER_LENS_API_PORT", "8080")),
        feed_port=int(os.environ.get("ROUTER_LENS_FEED_PORT", "8090")),
        stats_poll_seconds=float(os.environ.get("ROUTER_LENS_STATS_POLL_SECONDS", "10")),
        first_byte_timeout=float(os.environ.get("ROUTER_LENS_FIRST_BYTE_TIMEOUT", "45")),
        idle_timeout=float(os.environ.get("ROUTER_LENS_IDLE_TIMEOUT", "45")),
        prices=prices,
        model_tiers=tiers,
    )
