from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)


@dataclass(frozen=True)
class Config:
    discord_token: str
    guild_id: int | None
    deals_channel_id: int | None
    scan_interval_minutes: int
    default_discount_threshold_percent: float
    database_path: Path
    http_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token or token == "put_your_discord_bot_token_here":
            raise RuntimeError(
                "DISCORD_TOKEN is missing. Copy .env.example to .env and add your bot token."
            )

        database_path = Path(os.getenv("DATABASE_PATH", "data/pikapromo.sqlite3"))
        database_path.parent.mkdir(parents=True, exist_ok=True)

        return cls(
            discord_token=token,
            guild_id=_optional_int(os.getenv("DISCORD_GUILD_ID")),
            deals_channel_id=_optional_int(os.getenv("DEALS_CHANNEL_ID")),
            scan_interval_minutes=int(os.getenv("SCAN_INTERVAL_MINUTES", "360")),
            default_discount_threshold_percent=float(
                os.getenv("DEFAULT_DISCOUNT_THRESHOLD_PERCENT", "15")
            ),
            database_path=database_path,
            http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "25")),
        )
