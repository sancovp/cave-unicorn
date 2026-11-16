"""cave-unicorn — the UNICORN distribution module of the SANCREV SDK.

An L9 cave-auxiliary lib (same layer law as cave-discord): connects produced
blogs into the live website and carries the setup interface for the
distribution stack. CAVE consumes this lib via cave_seam; this lib never
imports cave at module level.
"""

from .config import init_config, load_config, set_key
from .site import (publish_file, publish_funnel_file, render_post, insert_card,
                   split_front, slugify)
from .publish import fire_site_publish, funnel_slug_of
from .cave_seam import build_site_publish_automation, register_with_cave, emit_schema
from .crosslink import chapter_nav_links, render_chapter_nav, kind_of
from .overviews import facet_of, facet_overview, regenerate_overviews
from .update_wire import assert_guild_allowed, notify_publish, SACRED_GUILDS

__all__ = [
    "init_config", "load_config", "set_key",
    "publish_file", "publish_funnel_file", "render_post", "insert_card",
    "split_front", "slugify",
    "fire_site_publish", "funnel_slug_of",
    "build_site_publish_automation", "register_with_cave", "emit_schema",
    "chapter_nav_links", "render_chapter_nav", "kind_of",
    "facet_of", "facet_overview", "regenerate_overviews",
    "assert_guild_allowed", "notify_publish", "SACRED_GUILDS",
]
