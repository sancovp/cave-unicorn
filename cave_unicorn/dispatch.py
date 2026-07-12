"""HEAVEN/MiniMax agent dispatch — the same proven pattern as
cave.core.publishing.blog_organ_nightly._run_agent (deliberately COPIED, not
imported: cave-unicorn is L9 and never depends on L7/cave — the layer law).

Build a HeavenAgentConfig from the SAME journal_agent_config.json the
WakingDreamer service agents read (model + anthropic_api_url), equip BashTool
so the agent reads sources / writes deliverables itself, run the prompt.
Heaven resolves the provider key internally — no provider creds constructed
here, the host OAuth token is never touched.

WALL-CLOCK TIMEOUT (2026-07-12): the dispatch runs in a CHILD PROCESS the
parent kills on deadline. This is deliberate and load-bearing — the hang
caught live that day (85 minutes of silence after 2 completed API calls) was
a blocking unix-socket read wedged ON the event-loop thread, so no in-process
timeout (asyncio.wait_for, signal handlers on a worker thread) can ever fire
for this class. Only a separate process can be killed from outside. On
timeout the child is terminated and run_agent returns a LOUD error — never a
silent retry, never a fallback.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import tempfile
from pathlib import Path
from typing import Callable, Tuple

logger = logging.getLogger(__name__)

HEAVEN_DATA_DIR = Path(os.environ.get("HEAVEN_DATA_DIR", "/tmp/heaven_data"))
MINIMAX_CONFIG_PATH = HEAVEN_DATA_DIR / "journal_agent_config.json"

# Healthy organ runs complete in 5-25 minutes; 45 minutes is unambiguous hang
# territory (the caught hang sat 85+ minutes and would have sat forever).
DEFAULT_DISPATCH_TIMEOUT_S = int(
    os.environ.get("UNICORN_DISPATCH_TIMEOUT_S", "2700"))


def _minimax_model_config() -> dict:
    if MINIMAX_CONFIG_PATH.exists():
        try:
            return json.loads(MINIMAX_CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            logger.error("unreadable minimax config at %s", MINIMAX_CONFIG_PATH,
                         exc_info=True)
    return {}


def _dispatch_child(config_kwargs: dict, prompt: str, max_tool_calls: int,
                    result_path: str) -> None:
    """Child-process body: run the heaven dispatch, write the outcome JSON.

    Module-level (picklable for the spawn context). Heavy imports happen HERE
    so the parent never pays them and the child starts from a clean
    interpreter. Writes {"ok": bool, "error": str} to result_path; a missing
    result file means the child died before finishing — the parent reports
    that loudly.
    """
    import asyncio

    out = {"ok": False, "error": "child died before writing a result"}
    try:
        from heaven_base.baseheavenagent import BaseHeavenAgent, HeavenAgentConfig
        from heaven_base.unified_chat import UnifiedChat
        from heaven_base.tools import BashTool
        from heaven_base.docs.examples.heaven_callbacks import BackgroundEventCapture

        config = HeavenAgentConfig(tools=[BashTool], **config_kwargs)

        async def _dispatch():
            agent = BaseHeavenAgent(config=config, unified_chat=UnifiedChat(),
                                    max_tool_calls=max_tool_calls)
            capture = BackgroundEventCapture()
            return await agent.run(prompt=prompt, heaven_main_callback=capture)

        asyncio.run(_dispatch())
        out = {"ok": True, "error": ""}
    except Exception as e:  # heaven dispatch failure — captured, never fallback
        import traceback
        out = {"ok": False,
               "error": f"heaven minimax dispatch failed: {e}\n"
                        + traceback.format_exc()}
    Path(result_path).write_text(json.dumps(out))


def run_agent(prompt: str, name: str = "unicorn_socials",
              max_tool_calls: int = 40,
              timeout_s: int | None = None,
              _child_target: Callable | None = None) -> Tuple[bool, str, str]:
    """Dispatch a heaven/minimax BashTool agent with ``prompt``.

    Returns (ok, error, model); error is "" on success. Sync-callable (cron
    code_pointer). The dispatch runs in a spawned child process killed after
    ``timeout_s`` (default DEFAULT_DISPATCH_TIMEOUT_S) — see the module
    docstring for why an in-process timeout cannot work. ``_child_target``
    exists for tests only (a stand-in child body).
    """
    timeout_s = DEFAULT_DISPATCH_TIMEOUT_S if timeout_s is None else timeout_s
    cfg = _minimax_model_config()
    model = cfg.get("model", "")
    api_url = cfg.get("extra_model_kwargs", {}).get("anthropic_api_url", "")
    if not (model and api_url):
        return (False,
                f"minimax model config missing/incomplete at {MINIMAX_CONFIG_PATH} "
                f"(model={model!r}, anthropic_api_url={api_url!r})", model)

    config_kwargs = dict(
        name=name,
        system_prompt="",  # the whole instruction is the prompt body
        model=model,
        use_uni_api=cfg.get("use_uni_api", False),
        max_tokens=cfg.get("max_tokens", 8000),
        extra_model_kwargs={"anthropic_api_url": api_url},
        **({"provider": cfg["provider"]} if cfg.get("provider") else {}),
    )

    fd, result_path = tempfile.mkstemp(prefix="unicorn_dispatch_", suffix=".json")
    os.close(fd)
    os.unlink(result_path)  # the child writing it back IS the success signal
    ctx = multiprocessing.get_context("spawn")  # clean interpreter, fork-safe
    proc = ctx.Process(target=_child_target or _dispatch_child,
                       args=(config_kwargs, prompt, max_tool_calls, result_path))
    try:
        proc.start()
        proc.join(timeout_s)
        if proc.is_alive():
            proc.terminate()
            proc.join(5)
            if proc.is_alive():
                proc.kill()
                proc.join(5)
            logger.error("unicorn dispatch %r exceeded %ss wall-clock — KILLED",
                         name, timeout_s)
            return (False,
                    f"dispatch exceeded wall-clock timeout {timeout_s}s and was "
                    "KILLED (the 2026-07-12 hang class: a blocking IPC read wedged "
                    "on the event-loop thread — only an out-of-process kill can "
                    "catch it). Artifacts from a killed run must fail the "
                    "freshness check.", model)
        result_file = Path(result_path)
        if not result_file.exists():
            return (False,
                    f"dispatch child exited (code {proc.exitcode}) without "
                    "writing a result — child crashed", model)
        out = json.loads(result_file.read_text())
        return bool(out.get("ok")), str(out.get("error", "")), model
    finally:
        Path(result_path).unlink(missing_ok=True)
