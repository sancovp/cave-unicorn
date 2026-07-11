"""Unicorn config — the persistent state behind the setup interface.

One JSON file at ``$HEAVEN_DATA_DIR/unicorn_config.json`` holds the
distribution-stack settings the module publishes against. The CLI (``cave-unicorn
init/show/set``) is the setup interface over this file; ``site.publish_file`` and
``publish.fire_site_publish`` consume it.

Keys (all present after ``init``):
  - ``site_root``     : absolute path of the website git checkout (the aisaac repo).
  - ``blog_dir``      : blog directory relative to site_root (posts + index.html live here).
  - ``site_base_url`` : public base URL of the site (for reporting the live post URL).
  - ``remote``/``branch`` : git push target of the site repo.
  - ``push``          : default push behavior for publishes (CLI/automation can override).
  - ``default_tags``  : index-card tags applied when a publish gives none.
  - ``discord_announce``/``discord_channel`` : after a PUSHED publish, announce
    the live URLs in Discord via cave_discord (the announce leg; off by default).

FAIL LOUD: ``load_config`` raises if the file is absent (run ``cave-unicorn init``);
it never invents a config silently.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Any] = {
    "site_root": "/home/GOD/aisaac",
    "blog_dir": "blog",
    "site_base_url": "https://sancovp.github.io/aisaac",
    "remote": "origin",
    "branch": "main",
    "push": False,
    "default_tags": ["unicorn"],
    "discord_announce": False,
    "discord_channel": "coglog",
}


def config_path(path: Optional[str] = None) -> Path:
    if path:
        return Path(path)
    heaven = os.environ.get("HEAVEN_DATA_DIR", "/tmp/heaven_data")
    return Path(heaven) / "unicorn_config.json"


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Read the config. Raises FileNotFoundError with the fix if absent."""
    p = config_path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"unicorn config missing at {p} — run `cave-unicorn init` "
            f"(or python3 -m cave_unicorn init) to create it"
        )
    cfg = json.loads(p.read_text())
    missing = [k for k in DEFAULTS if k not in cfg]
    if missing:
        raise KeyError(
            f"unicorn config at {p} is missing keys: {', '.join(missing)} — "
            f"run `cave-unicorn set <key> <value>` or re-init"
        )
    return cfg


def init_config(path: Optional[str] = None, force: bool = False,
                **overrides: Any) -> Dict[str, Any]:
    """Write a fresh config from DEFAULTS (+overrides). Refuses to clobber unless force."""
    p = config_path(path)
    if p.exists() and not force:
        raise FileExistsError(f"unicorn config already exists at {p} (use force to rewrite)")
    cfg = {**DEFAULTS, **overrides}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    return cfg


def set_key(key: str, value: Any, path: Optional[str] = None) -> Dict[str, Any]:
    """Set one key on the existing config (must exist; must be a known key)."""
    cfg = load_config(path)
    if key not in DEFAULTS:
        raise KeyError(f"unknown unicorn config key {key!r} (known: {', '.join(DEFAULTS)})")
    cfg[key] = value
    p = config_path(path)
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    return cfg
