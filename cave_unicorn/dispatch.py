"""HEAVEN/MiniMax agent dispatch — the same proven pattern as
cave.core.publishing.blog_organ_nightly._run_agent (deliberately COPIED, not
imported: cave-unicorn is L9 and never depends on L7/cave — the layer law).

Build a HeavenAgentConfig from the SAME journal_agent_config.json the
WakingDreamer service agents read (model + anthropic_api_url), equip BashTool
so the agent reads sources / writes deliverables itself, run the prompt.
Heaven resolves the provider key internally — no provider creds constructed
here, the host OAuth token is never touched.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

HEAVEN_DATA_DIR = Path(os.environ.get("HEAVEN_DATA_DIR", "/tmp/heaven_data"))
MINIMAX_CONFIG_PATH = HEAVEN_DATA_DIR / "journal_agent_config.json"


def _minimax_model_config() -> dict:
    if MINIMAX_CONFIG_PATH.exists():
        try:
            return json.loads(MINIMAX_CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            logger.error("unreadable minimax config at %s", MINIMAX_CONFIG_PATH,
                         exc_info=True)
    return {}


def run_agent(prompt: str, name: str = "unicorn_socials",
              max_tool_calls: int = 40) -> Tuple[bool, str, str]:
    """Dispatch a heaven/minimax BashTool agent with ``prompt``.

    Returns (ok, error, model); error is "" on success. Sync-callable (cron
    code_pointer) — wraps the async dispatch with asyncio.run.
    """
    cfg = _minimax_model_config()
    model = cfg.get("model", "")
    api_url = cfg.get("extra_model_kwargs", {}).get("anthropic_api_url", "")
    if not (model and api_url):
        return (False,
                f"minimax model config missing/incomplete at {MINIMAX_CONFIG_PATH} "
                f"(model={model!r}, anthropic_api_url={api_url!r})", model)

    try:
        from heaven_base.baseheavenagent import BaseHeavenAgent, HeavenAgentConfig
        from heaven_base.unified_chat import UnifiedChat
        from heaven_base.tools import BashTool
        from heaven_base.docs.examples.heaven_callbacks import BackgroundEventCapture
    except ImportError as e:
        logger.error("heaven-framework not importable: %s", e, exc_info=True)
        return False, f"heaven-framework not importable: {e}", model

    config = HeavenAgentConfig(
        name=name,
        system_prompt="",  # the whole instruction is the prompt body
        tools=[BashTool],
        model=model,
        use_uni_api=cfg.get("use_uni_api", False),
        max_tokens=cfg.get("max_tokens", 8000),
        extra_model_kwargs={"anthropic_api_url": api_url},
        **({"provider": cfg["provider"]} if cfg.get("provider") else {}),
    )

    async def _dispatch():
        agent = BaseHeavenAgent(config=config, unified_chat=UnifiedChat(),
                                max_tool_calls=max_tool_calls)
        capture = BackgroundEventCapture()
        return await agent.run(prompt=prompt, heaven_main_callback=capture)

    try:
        asyncio.run(_dispatch())
        return True, "", model
    except Exception as e:  # heaven dispatch failure — captured, never fallback
        logger.error("heaven minimax dispatch failed: %s", e, exc_info=True)
        return False, f"heaven minimax dispatch failed: {e}", model
