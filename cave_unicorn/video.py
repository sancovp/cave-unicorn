"""fire_video_render — blog post → explainer video (CronAutomation code_pointer).

The FOURTH nightly organ (after blog 02:00 → site 02:37 → socials 03:07 →
images 03:37): scan nodes with ``images_rendered: true`` and no
``video_rendered`` → for each, dispatch a HEAVEN/MINIMAX video-producer agent
(the proven remotion + TTS + excalidraw + ffmpeg pipeline skills) that
produces ``final.mp4`` for the blog → FRESHNESS GATE (the artifact must
exist AND carry mtime >= dispatch start — bare existence passes on a stale
file from a prior/killed run, the ok-report-no-artifact trap the blog
organ's ``_artifact_fresh`` closed on 2026-07-12) → flip
``video_rendered``/``video_path`` (or ``video_error``). Never raises.

Direct mode: fire_video_render(blog_md_path=..., images_dir=..., out_dir=...).

INERT BY DEFAULT: the CronAutomation schema exists
(cave_seam.build_video_render_automation) but is never auto-emitted into the
hot-reload dir — the commander enables it explicitly
(``cave-unicorn enable-automation --which video``).

DISPATCH (Isaac 2026-07-13, correcting a wrong first build — verbatim: "why
is that running on anthropic? it needs to run on minimax. on heaven... wtf is
run_claude_agent?"): this dispatches on HEAVEN/MINIMAX, the EXACT SAME proven
pattern as ``cave/core/publishing/blog_organ_nightly.py`` (which itself
mirrors the WakingDreamer service agents) — a ``BaseHeavenAgent`` built from a
``HeavenAgentConfig`` (minimax model + ``anthropic_api_url`` read from
``$HEAVEN_DATA_DIR/journal_agent_config.json``), equipped with ``BashTool``,
run in a spawned CHILD PROCESS with a wall-clock timeout (heaven has no
in-process timeout for a wedged event-loop-thread IPC read — only an
out-of-process kill catches that hang class). Heaven resolves the MiniMax
provider key INTERNALLY; no provider creds are constructed in this module, so
the host OAuth token is never touched. The FIRST build of this module shelled
out to the raw ``claude`` CLI with spoofed ``ANTHROPIC_BASE_URL``/
``ANTHROPIC_AUTH_TOKEN`` env vars to redirect it at MiniMax — a fragile,
ad-hoc, un-proven mechanism duplicating a problem the blog organ had already
solved cleanly on HEAVEN, in this same repo, the same day. That approach is
retired; do not reintroduce it.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .publish import _carton

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = os.environ.get(
    "VIDEO_ORGAN_PROMPT_PATH",
    "/home/GOD/gnosys-plugin-v2/doc-mirror-system/plugin/skills/doc-mirror-prompts/"
    "resources/prompts/skill2framework/video-organ/video-from-blog/SKILL.md",
)
RENDER_SCRIPT = os.environ.get(
    "EXCALIDRAW_RENDER_SCRIPT",
    "/tmp/heaven_data/skills/excalidraw-render/scripts/render.py",
)
EXPECTED_VIDEO = "final.mp4"

HEAVEN_DATA_DIR = Path(os.environ.get("HEAVEN_DATA_DIR", "/tmp/heaven_data"))
MINIMAX_CONFIG_PATH = HEAVEN_DATA_DIR / "journal_agent_config.json"

# Video runs (TTS + remotion render + ffmpeg) are the slowest organ leg;
# 45 minutes is the same unambiguous-hang deadline the other dispatches use.
DEFAULT_VIDEO_TIMEOUT_S = int(os.environ.get("UNICORN_VIDEO_TIMEOUT_S", "2700"))


def _minimax_model_config() -> dict:
    """Read minimax model config from journal_agent_config.json (the WD agents'
    config — SAME reader as blog_organ_nightly's ``_minimax_model_config``).
    Returns {} if absent/unreadable."""
    if MINIMAX_CONFIG_PATH.exists():
        try:
            return json.loads(MINIMAX_CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _video_mcp_servers() -> dict:
    """Playwright MCP for the video-producer agent (Isaac 2026-07-13, verbatim: "this agent
    needs playwright mcp, bashtool, networkedittool"). Mirrors OM's own load_mcp_servers
    shape (onionmorph/runtime.py) — heaven's mcp_servers dict: {name: {command,args,transport}}.
    Verified runnable in this container: `npx -y @playwright/mcp@latest --version` -> 0.0.78, rc=0.
    Needed because the pipeline's own preview step is a localhost:3000 Remotion dev server the
    agent must actually LOOK AT (frame-by-frame), not just shell out to a headless render and
    hope — the same need moviola-sweatloupe's QC loop names (Playwright screenshots the preview)."""
    return {"playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@latest"],
                           "transport": "stdio"}}


# WHO THE AGENT IS (Isaac 2026-07-13, verbatim mandate after five powerpoint-shaped renders:
# "this has to be EXPLICIT in the system prompt of the agent, as its core way its persona works.
# WHO THE AGENT IS is the guy who animates everything that is mentioned, this way.").
# Instructions in a dispatch brief did NOT cause the behavior; the persona in the system prompt
# is the mechanism-ladder rung that must carry it.
VIDEO_AGENT_SYSTEM_PROMPT = """You are the ANIMATOR. Who you are: the guy who animates every single
mentioned thing AS it is mentioned. That is your core way of working, not a style option. When the
narration says a node, a wall, a limit, a thread, a reset, a file — that thing APPEARS ON SCREEN AS
A DRAWN, MOVING ELEMENT at the moment the word is spoken, and it TRANSFORMS as the sentence acts on
it. A slide with text on it — however the text enters — is not your work product.

HOW YOU ACHIEVE THAT — YOU DO NOT AUTHOR A COMPOSITION. There is a proven BASE at
/tmp/remotion-test/src/base/ that already guarantees the animation. Your job is to FILL its template:
you produce ONE data file (a ShotList, exactly like src/base/example.ts) where each sentence gets a
Beat with a `visual` from the base's menu that DEPICTS what it mentions. The base renders it into a
fully-animated video. Because every visual kind in the base is motion by construction, a powerpoint
is not expressible — the law is enforced by the code, not your discipline.

TWO ABSOLUTE LAWS OF YOUR WORKSHOP:
1. ONE DIRECTORY. You work ONLY in /tmp/remotion-test/. It contains the base template
   (src/base/: README.md, types.ts, example.ts), the remotion rules, the audio, and the working
   project. You never build a video anywhere else; the final.mp4 is written to the requested output.
2. THE BASE IS THE ONLY WAY. You NEVER develop or even use Remotion without it. You do NOT write React
   or design motion by hand — you READ src/base/README.md + types.ts + example.ts FROM THE START, then
   fill a ShotList and render via `npx remotion render src/base/Root.tsx AisaacVideo`. There is a
   template to use; it must be used. Period. Do not modify the engine files under src/base/.
"""


def _dispatch_child(config_kwargs: dict, prompt: str, max_tool_calls: int,
                    result_path: str) -> None:
    """Child-process body: run the heaven dispatch, write the outcome JSON.

    Module-level (picklable for the spawn context). Heavy imports happen HERE.

    TOOLS (Isaac 2026-07-13, correcting the first build which equipped ONLY BashTool,
    mirroring blog_organ_nightly.py's minimal harness without checking whether that was
    even the right reference): mirrors OM's OWN heaven-agent construction
    (onionmorph/runtime.py build_om_agent_config) — BashTool (shell: TTS/ffmpeg/npx) +
    NetworkEditTool (heaven's precise view/create/str_replace/undo_edit file tool — the
    Edit-tool analog, for iterating the Remotion .tsx composition) + Playwright MCP (loaded
    via mcp_servers, the SAME mechanism OM uses for its own MCP servers — the agent can
    actually navigate to the localhost:3000 preview and look at rendered frames, not just
    blind-shell `npx remotion render`). NOT equipped: carton (Isaac: "it should be being
    sent files already" — blog_md_path/images_dir are passed in directly, no graph lookup
    needed for this job).
    """
    import asyncio

    out = {"ok": False, "error": "child died before writing a result"}
    try:
        from heaven_base.baseheavenagent import BaseHeavenAgent, HeavenAgentConfig
        from heaven_base.unified_chat import UnifiedChat
        from heaven_base.tools.bash_tool import BashTool
        from heaven_base.tools.network_edit_tool import NetworkEditTool
        from heaven_base.docs.examples.heaven_callbacks import BackgroundEventCapture

        config = HeavenAgentConfig(tools=[BashTool, NetworkEditTool],
                                   mcp_servers=_video_mcp_servers(), **config_kwargs)

        async def _dispatch():
            agent = BaseHeavenAgent(
                config=config,
                unified_chat=UnifiedChat(),
                max_tool_calls=max_tool_calls,
            )
            capture = BackgroundEventCapture()
            return await agent.run(prompt=prompt, heaven_main_callback=capture)

        asyncio.run(_dispatch())
        out = {"ok": True, "error": ""}
    except Exception as e:  # heaven dispatch failure — capture literally, do NOT fall back
        import traceback
        out = {"ok": False,
               "error": f"heaven minimax dispatch failed: {e}\n"
                        + traceback.format_exc()}
    Path(result_path).write_text(json.dumps(out))


def run_heaven_agent(prompt: str, timeout: int = DEFAULT_VIDEO_TIMEOUT_S,
                     max_tool_calls: int = 80,
                     _child_target=None) -> Dict[str, Any]:
    """Dispatch the video-producer agent on HEAVEN/MINIMAX. Never raises.

    SAME proven pattern as blog_organ_nightly._run_agent: read minimax model
    config from journal_agent_config.json (VIDEO_ORGAN_MODEL env overrides the
    model, mirroring BLOG_ORGAN_MODEL), spawn a clean child process, kill it on
    wall-clock timeout (the only thing that can catch a wedged heaven IPC
    read). Returns {"ok", "error"}.
    """
    cfg = _minimax_model_config()
    model = os.environ.get("VIDEO_ORGAN_MODEL") or cfg.get("model", "")
    api_url = cfg.get("extra_model_kwargs", {}).get("anthropic_api_url", "")
    if not (model and api_url):
        return {"ok": False,
                "error": f"minimax model config missing/incomplete at "
                         f"{MINIMAX_CONFIG_PATH} (model={model!r}, "
                         f"anthropic_api_url={api_url!r})"}

    config_kwargs = dict(
        name="video_organ",
        system_prompt=VIDEO_AGENT_SYSTEM_PROMPT,
        model=model,
        use_uni_api=cfg.get("use_uni_api", False),
        max_tokens=int(os.environ.get("VIDEO_ORGAN_MAX_TOKENS", "16000")),
        extra_model_kwargs={"anthropic_api_url": api_url},
        **({"provider": cfg["provider"]} if cfg.get("provider") else {}),
    )

    fd, result_path = tempfile.mkstemp(prefix="video_organ_dispatch_", suffix=".json")
    os.close(fd)
    os.unlink(result_path)  # the child writing it back IS the success signal
    ctx = multiprocessing.get_context("spawn")  # clean interpreter, fork-safe
    proc = ctx.Process(target=_child_target or _dispatch_child,
                       args=(config_kwargs, prompt, max_tool_calls, result_path))
    try:
        proc.start()
        proc.join(timeout)
        if proc.is_alive():
            proc.terminate()
            proc.join(5)
            if proc.is_alive():
                proc.kill()
                proc.join(5)
            logger.error("video agent dispatch exceeded %ss wall-clock — KILLED", timeout)
            return {"ok": False,
                    "error": f"dispatch exceeded wall-clock timeout {timeout}s and "
                             "was KILLED"}
        result_file = Path(result_path)
        if not result_file.exists():
            return {"ok": False,
                    "error": f"dispatch child exited (code {proc.exitcode}) without "
                             "writing a result — child crashed"}
        out = json.loads(result_file.read_text())
        if not out.get("ok"):
            logger.error("video agent (heaven minimax) failed: %s", out.get("error"))
        return {"ok": bool(out.get("ok")), "error": str(out.get("error", ""))}
    finally:
        Path(result_path).unlink(missing_ok=True)


def build_prompt(blog_md_path: str, images_dir: str, out_dir: str) -> str:
    raw = Path(DEFAULT_PROMPT_PATH).read_text()
    marker = "## PROMPT"
    body = raw.split(marker, 1)[1] if marker in raw else raw
    return (body.replace("{blog_md_path}", blog_md_path)
                .replace("{images_dir}", images_dir or "(none rendered)")
                .replace("{out_dir}", out_dir)
                .replace("{render_script}", RENDER_SCRIPT))


def _artifact_fresh(path: Path, t0: float) -> bool:
    """True iff ``path`` exists AND was written at/after dispatch start ``t0``.

    The blog organ's freshness law (caught live 2026-07-12): a halted run
    'succeeded' against a STALE artifact from a prior run — only a write
    newer than this dispatch counts as the deliverable.
    """
    return path.exists() and path.stat().st_mtime >= t0


def render_video_for_blog(blog_md_path: str, images_dir: str = "",
                          out_dir: str | None = None) -> Dict[str, Any]:
    """Render one blog's video; verify final.mp4 is FRESH. Returns a status dict."""
    if not Path(blog_md_path).exists():
        return {"status": "failed", "error": f"blog md not found: {blog_md_path}",
                "video_path": ""}
    if out_dir:
        out = Path(out_dir)
    elif images_dir:
        # The images organ renders into <pack dir>/images; the video is its
        # sibling <pack dir>/video, so one slug's artifacts stay together.
        out = Path(images_dir).parent / "video"
    else:
        out = Path(blog_md_path).parent / "video"
    out.mkdir(parents=True, exist_ok=True)
    video = out / EXPECTED_VIDEO

    prompt = build_prompt(blog_md_path, images_dir, str(out))
    logger.info("unicorn video: dispatching video-producer for %s", out)
    # 2s allowance: st_mtime granularity can truncate a fresh write to just
    # below a float time.time() — the gate targets PRIOR-run artifacts
    # (minutes/hours stale), never a same-second write.
    t0 = time.time() - 2.0
    res = run_heaven_agent(prompt)

    if not res["ok"] or not _artifact_fresh(video, t0):
        error = res["error"] or (
            f"agent finished but {video} was not freshly written "
            "(missing, or mtime predates this dispatch)")
        logger.error("unicorn video: failed — %s", error)
        return {"status": "failed", "error": error[:300], "video_path": str(video)}

    logger.info("unicorn video: rendered %s", video)
    return {"status": "rendered", "video_path": str(video), "video_dir": str(out)}


def _images_without_video(graph) -> List[Dict[str, Any]]:
    """images_rendered nodes with an output md that have no video yet.

    Framework-first ordering: the video organ only fires AFTER the images
    organ flipped images_rendered — the video reuses those rendered images.
    LIMIT 5: video runs are the most expensive leg; the rest retry next scan.
    """
    rows = graph.execute_query(
        "MATCH (c:Wiki) WHERE c.images_rendered = true "
        "AND (c.output_path IS NOT NULL OR c.output_md_path IS NOT NULL) "
        "AND c.video_rendered IS NULL "
        "RETURN c.n AS n, properties(c) AS p LIMIT 5",
        {},
    )
    return [{"concept": r.get("n"), "props": dict(r.get("p") or {})}
            for r in rows or [] if r.get("n")]


def fire_video_render(**kwargs: Any) -> Dict[str, Any]:
    """CronAutomation code_pointer — render videos for image-complete blogs.

    kwargs (direct mode): blog_md_path (+ images_dir, out_dir). Scan mode: none.
    """
    if kwargs.get("blog_md_path"):
        return render_video_for_blog(kwargs["blog_md_path"],
                                     kwargs.get("images_dir", ""),
                                     kwargs.get("out_dir"))

    graph, set_props, _q = _carton()
    if graph is None:
        return {"status": "no_connection"}

    pending = _images_without_video(graph)
    if not pending:
        return {"status": "no_pending"}

    results: List[Dict[str, Any]] = []
    for item in pending:
        concept, props = item["concept"], item["props"]
        md = props.get("output_path") or props.get("output_md_path") or ""
        report = render_video_for_blog(md, props.get("images_dir", ""))
        if report["status"] == "rendered":
            flip = {"video_rendered": True, "video_path": report["video_path"],
                    "video_rendered_at": datetime.now().isoformat()}
            if props.get("video_error"):
                # An earlier attempt failed and left its error on the node;
                # a healthy rendered node must not carry a stale error string.
                flip["video_error"] = ""
            set_props(concept, flip, mode="merge", shared_connection=graph)
        else:
            set_props(concept, {"video_error": report["error"][:200]},
                      mode="merge", shared_connection=graph)
        results.append({"concept": concept, **report})

    rendered = sum(1 for r in results if r["status"] == "rendered")
    return {"status": "done", "rendered": rendered,
            "failed": len(results) - rendered, "results": results}
