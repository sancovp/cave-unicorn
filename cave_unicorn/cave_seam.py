"""The CAVE seam — import-if-present (same law as cave_discord.cave_seam):
cave-unicorn never imports cave at module level; L7 (CAVE) consumes L9 (this
lib), never the reverse. The schedule is **a cave CronAutomation** (registered
in the automation registry / the hot-JSON automations dir the Heart's
automation_hot_reload tick reads) — never a bare cron.

Registration surfaces:
  - ``register_with_cave(cave_agent)`` — on a LIVE CAVEAgent (sancrev boot path).
  - ``emit_schema()`` — write the AutomationSchema JSON straight into the
    hot-JSON automations dir (default /tmp/heaven_data/automations/) so the
    running agent hot-reloads it; the CLI's ``enable-automation`` uses this.

Verified schema shape against the live registration blog_organ_nightly.json:
{name, description, schedule (cron string), code_pointer (dot-form module.func
invoked as func(**code_args)), code_args, one_shot, priority, tags, enabled}.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Nightly at 02:37 — AFTER the 02:00 blog organ writes, off the :00/:30 marks.
DEFAULT_SCHEDULE = "37 2 * * *"


def build_site_publish_automation(
    schedule: str = DEFAULT_SCHEDULE,
    code_args: Optional[Dict[str, Any]] = None,
    name: str = "unicorn_site_publish",
) -> Dict[str, Any]:
    """The AutomationSchema-shaped spec for the site publisher (same shape as
    blog_organ_nightly.json). ``code_args`` become fire_site_publish kwargs
    (e.g. {"push": true})."""
    return {
        "name": name,
        "description": "UNICORN site publisher: Blog_Request nodes done but not "
                       "site-published -> render into the live blog + index card "
                       "-> commit/push -> flip site_published on the node.",
        "schedule": schedule,
        "code_pointer": "cave_unicorn.publish.fire_site_publish",
        "code_args": dict(code_args or {}),
        "one_shot": False,
        "priority": 4,
        "tags": ["publishing", "blog", "unicorn", "distribution"],
        "enabled": True,
    }


def build_socials_pack_automation(
    schedule: str = "7 3 * * *",  # nightly 03:07 — after the 02:37 site publish
    code_args: Optional[Dict[str, Any]] = None,
    name: str = "unicorn_socials_pack",
) -> Dict[str, Any]:
    """AutomationSchema spec for the socials organ (posts + image prompts)."""
    return {
        "name": name,
        "description": "UNICORN socials organ: site_published blogs without a "
                       "socials pack -> heaven/minimax agent writes the "
                       "twitter/linkedin/discord posts + image prompts to the "
                       "socials_queue -> flip socials_packed on the node.",
        "schedule": schedule,
        "code_pointer": "cave_unicorn.socials.fire_socials_pack",
        "code_args": dict(code_args or {}),
        "one_shot": False,
        "priority": 4,
        "tags": ["publishing", "socials", "unicorn", "distribution"],
        "enabled": True,
    }


def build_socials_images_automation(
    schedule: str = "37 3 * * *",  # nightly 03:37 — after the 03:07 socials pack
    code_args: Optional[Dict[str, Any]] = None,
    name: str = "unicorn_socials_images",
) -> Dict[str, Any]:
    """AutomationSchema spec for the image renderer (packs -> real PNGs)."""
    return {
        "name": name,
        "description": "UNICORN image renderer: socials packs without rendered "
                       "images -> claude -p excalidraw agent renders + verifies "
                       "hero/social-share/thumbnail PNGs -> flip images_rendered.",
        "schedule": schedule,
        "code_pointer": "cave_unicorn.images.fire_socials_images",
        "code_args": dict(code_args or {}),
        "one_shot": False,
        "priority": 4,
        "tags": ["publishing", "socials", "images", "unicorn", "distribution"],
        "enabled": True,
    }


def register_with_cave(cave_agent: Any, schedule: str = DEFAULT_SCHEDULE,
                       code_args: Optional[Dict[str, Any]] = None,
                       persist: bool = True) -> bool:
    """Register the site publisher on a live CAVEAgent's automation registry
    (import-if-present; returns False — never raises — when cave is absent or
    the agent has no automation surface)."""
    try:
        from cave.core.automation import AutomationSchema, CronAutomation  # type: ignore
    except ImportError:
        logger.error("cave not importable — cannot register unicorn automation",
                     exc_info=True)
        return False

    spec = build_site_publish_automation(schedule=schedule, code_args=code_args)
    try:
        schema = AutomationSchema(**spec)
        registry = getattr(cave_agent, "automation_registry", None)
        if registry is None:
            logger.error("cave agent has no automation_registry — not registered")
            return False
        automation = CronAutomation(schema=schema)
        registry.register(automation)
        if persist and hasattr(registry, "save_schema"):
            registry.save_schema(schema)
        logger.info("unicorn: registered automation %s", spec["name"])
        return True
    except Exception:
        logger.error("unicorn: automation registration failed", exc_info=True)
        return False


def emit_spec(spec: Dict[str, Any], automations_dir: Optional[str] = None) -> str:
    """Write one AutomationSchema JSON into the hot-reload automations dir."""
    d = Path(automations_dir
             or os.environ.get("CAVE_AUTOMATIONS_DIR", "/tmp/heaven_data/automations"))
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{spec['name']}.json"
    path.write_text(json.dumps(spec, indent=2) + "\n")
    logger.info("unicorn: emitted automation schema %s", path)
    return str(path)


def emit_schema(automations_dir: Optional[str] = None,
                schedule: str = DEFAULT_SCHEDULE,
                code_args: Optional[Dict[str, Any]] = None) -> str:
    """Emit the site-publish automation schema; returns the path."""
    return emit_spec(build_site_publish_automation(schedule=schedule,
                                                   code_args=code_args),
                     automations_dir)
