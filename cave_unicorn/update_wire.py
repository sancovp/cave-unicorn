"""The UPDATE WIRE — after a publish lands, blast it to the membership #updates stream.

Isaac's design (verbatim): "the entire discord re-publish becomes a notification stream
in updates/news that says like '{trueagent} just published {thing} at {link}' etc etc we
just blast it to members like that." When the nightly absorber publishes a node, it ALSO
posts that one line to the membership Discord's #updates channel.

This module NEVER reimplements the discord machinery — it CALLS
``discord_hydrate.notify_published`` (integration/cave-discord-fork), which owns the
RestExecutor + the verbatim "{actor} just published {thing} at {link}" template.

CONFIG-DRIVEN + OPT-IN (both keys off by default):
  - ``notify_actor``          : the brand/agent name posted as {actor}.
  - ``updates_guild_config``  : path to the guild-config JSON (token, guild_id,
    channels{name:id}) whose #updates channel the line lands in.
  Either absent/null ⟹ the wire is silently disabled (one log line), never a crash.

THE SACRED-GUILD GATE (a hard safety REFUSAL, not a soft skip): the wire RAISES if the
resolved target guild is a SACRED guild (TWI 1034897954542207116, GNOSYS
1439317050999705933) unless the guild config file explicitly carries ``"allow_live": true``
(nothing sets it today). The test-guild config is the only sanctioned notify target.

PURE CORE (no I/O): assert_guild_allowed (the gate).
THIN I/O: notify_publish (the wire entrypoint), _load_guild_config, _load_discord_hydrate.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# The SACRED guilds the wire must NEVER post to without an explicit allow_live override.
SACRED_GUILDS: Dict[str, str] = {
    "1034897954542207116": "TWI",
    "1439317050999705933": "GNOSYS",
}

# Where discord_hydrate lives (it is a loose module in the cave-discord-fork dir, NOT a
# pip package). Derived from THIS module's position in the monorepo so nothing is
# hard-coded; overridable via CAVE_DISCORD_FORK_DIR.
_DEFAULT_FORK_DIR = str(Path(__file__).resolve().parents[3] / "integration" / "cave-discord-fork")


def assert_guild_allowed(guild_id: str, allow_live: bool) -> None:
    """The gate. Raises RuntimeError if ``guild_id`` is a SACRED guild and not allow_live. PURE.

    A sacred guild (TWI / GNOSYS) may only be targeted when the guild config file
    explicitly sets ``"allow_live": true``; otherwise the wire REFUSES loudly rather
    than blast a publish line into a real community. A non-sacred guild always passes.
    """
    name = SACRED_GUILDS.get(str(guild_id))
    if name and not allow_live:
        raise RuntimeError(
            f"update wire REFUSES to post to the SACRED {name} guild ({guild_id}) — "
            f"the target guild config must set \"allow_live\": true to override "
            f"(nothing sets it today; the test guild is the only sanctioned target)"
        )


def _load_guild_config(path: str) -> Dict[str, Any]:
    """Read the guild-config JSON (token, guild_id, channels, optional allow_live). THIN I/O.

    Raises FileNotFoundError if the named path is absent — a configured-but-missing
    guild config is a real misconfiguration, surfaced loudly (never silently skipped)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"update wire: updates_guild_config points at {p}, which does not exist"
        )
    return json.loads(p.read_text())


def _load_discord_hydrate():
    """Load the discord_hydrate module (import-if-present). Returns it or None.

    discord_hydrate is a loose module (not a pip package), so it is first tried on the
    normal import path (in case it IS installed), then loaded DIRECTLY from its file at
    the cave-discord-fork dir (CAVE_DISCORD_FORK_DIR env, else the monorepo-derived
    default) via importlib — no global sys.path mutation. discord_hydrate imports only
    stdlib at module level, so a standalone file-load is safe. Returns None (never
    raises) when it cannot be found — the caller then disables the wire with a log line.
    """
    try:
        return importlib.import_module("discord_hydrate")
    except ImportError:
        pass
    fork_dir = os.environ.get("CAVE_DISCORD_FORK_DIR", _DEFAULT_FORK_DIR)
    module_path = os.path.join(fork_dir, "discord_hydrate.py")
    if not os.path.exists(module_path):
        logger.error("update wire: discord_hydrate not found (not installed; no file at %s)",
                     module_path)
        return None
    try:
        spec = importlib.util.spec_from_file_location("discord_hydrate", module_path)
        if spec is None or spec.loader is None:
            logger.error("update wire: could not build import spec for %s", module_path)
            return None
        module = importlib.util.module_from_spec(spec)
        # REGISTER in sys.modules BEFORE exec_module — REQUIRED, not optional: the
        # module defines @dataclass classes, and the dataclass machinery resolves
        # cls.__module__ via sys.modules; an unregistered module makes @dataclass raise
        # AttributeError('NoneType' object has no attribute '__dict__'). Do NOT remove
        # this line (a codenose 'syspath' warning here is a false positive — this is
        # sys.modules, the standard importlib file-load pattern, not sys.path).
        sys.modules["discord_hydrate"] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop("discord_hydrate", None)  # don't leave a half-loaded module
            raise
        return module
    except Exception as e:
        logger.error("update wire: discord_hydrate load failed from %s: %s",
                     module_path, e, exc_info=True)
        return None


def notify_publish(report: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Post one "{actor} just published {thing} at {link}" line to #updates. THIN I/O.

    ``report`` — a publish_file return dict (uses ``title`` + ``live_url``).
    ``cfg`` — the unicorn config (uses ``notify_actor`` + ``updates_guild_config``).

    Disabled (either config key absent/null) ⟹ {status: skipped} + one log line.
    The SACRED-GUILD GATE RAISES (propagates — a hard refusal) if the resolved guild is
    sacred without allow_live; a missing guild-config file also raises. Every OTHER error
    (import, network, missing token) is caught and returned as {status: failed} so the
    nightly flow never crashes and a blog is never un-published by a notify failure.
    """
    actor = cfg.get("notify_actor")
    guild_config_path = cfg.get("updates_guild_config")
    if not actor or not guild_config_path:
        logger.info("update wire disabled — notify_actor / updates_guild_config not set")
        return {"status": "skipped", "reason": "wire not configured"}

    # These two propagate (loud) by design: a missing named config, or the sacred gate.
    guild_cfg = _load_guild_config(guild_config_path)
    guild_id = str(guild_cfg.get("guild_id", ""))
    assert_guild_allowed(guild_id, bool(guild_cfg.get("allow_live", False)))

    dh = _load_discord_hydrate()
    if dh is None:
        return {"status": "failed", "error": "discord_hydrate not importable"}
    token = guild_cfg.get("token")
    channels = guild_cfg.get("channels") or {}
    if not token:
        logger.error("update wire: guild config %s has no token", guild_config_path)
        return {"status": "failed", "error": "guild config has no token"}

    try:
        executor = dh.RestExecutor(token)
        result = dh.notify_published(
            executor, channels, actor=str(actor),
            thing=str(report.get("title", "")), link=str(report.get("live_url", "")),
        )
        logger.info("update wire: notified #updates in guild %s", guild_id)
        return {"status": "notified", "guild_id": guild_id,
                "message_id": (result or {}).get("id")}
    except Exception as e:
        logger.error("update wire: notify failed: %s", e, exc_info=True)
        return {"status": "failed", "error": str(e)[:300]}
