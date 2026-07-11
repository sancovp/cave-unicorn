"""Discord announce leg — after a blog lands on the live site, announce it.

Uses the NEW discord library (cave_discord — the SANCREV SDK L9 lib driving the
cave-discord-mcp docker server), import-if-present: cave-unicorn never hard-
depends on it, and an announce failure never un-publishes a blog — it is
reported in the return dict (and logged with traceback), not raised.

Channel + guild come from the same ``discord_config.json`` the coglog publisher
reads ($HEAVEN_DATA_DIR/discord_config.json: token, guild_id, channels{name:id});
WHICH channel is the unicorn config's ``discord_channel`` key.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _discord_config() -> Dict[str, Any]:
    p = Path(os.environ.get("HEAVEN_DATA_DIR", "/tmp/heaven_data")) / "discord_config.json"
    if not p.exists():
        raise FileNotFoundError(f"discord config missing at {p}")
    return json.loads(p.read_text())


def announce_posts(reports: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Post one announcement message linking the published blogs.

    ``reports`` = publish_file return dicts (title + live_url used).
    Returns {status: announced|skipped|failed, ...}; never raises.
    """
    if not cfg.get("discord_announce"):
        return {"status": "skipped", "reason": "discord_announce disabled"}
    if not reports:
        return {"status": "skipped", "reason": "nothing published"}

    try:
        from cave_discord import DiscordMCPClient
    except ImportError as e:
        logger.error("cave_discord not importable — announce skipped: %s", e,
                     exc_info=True)
        return {"status": "failed", "error": f"cave_discord not importable: {e}"}

    try:
        dcfg = _discord_config()
        channel_name = cfg.get("discord_channel", "coglog")
        channel_id = dcfg.get("channels", {}).get(channel_name)
        if not channel_id:
            raise KeyError(f"channel {channel_name!r} not in discord_config.json")

        lines = ["**New on the blog** (published by the UNICORN module)"]
        lines += [f"- {r['title']}: {r['live_url']}" for r in reports]

        client = DiscordMCPClient(dcfg["token"], dcfg["guild_id"])
        client.start()
        try:
            result = client.send_message(channel_id, "\n".join(lines))
        finally:
            client.stop()
        if result.get("isError"):
            raise RuntimeError(f"discord send failed: {result}")
        logger.info("unicorn: announced %d post(s) to #%s", len(reports), channel_name)
        return {"status": "announced", "channel": channel_name, "posts": len(reports)}
    except Exception as e:
        logger.error("unicorn: discord announce failed: %s", e, exc_info=True)
        return {"status": "failed", "error": str(e)[:300]}
