"""fire_socials_images — render the socials pack's images (CronAutomation).

Scan: nodes with ``socials_packed: true`` and no ``images_rendered`` → for each,
run a ``claude -p`` agent (the coglog-publisher dispatch pattern) that
interprets the pack's IMAGE PROMPTS as rich excalidraw diagrams, renders them
with the proven Playwright render script, and visually verifies each PNG →
check hero/social-share/thumbnail exist → flip ``images_rendered``/
``images_dir`` (or ``images_error``). Never raises.

Direct mode: fire_socials_images(pack_path=..., blog_md_path=..., out_dir=...).
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .publish import _carton

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = os.environ.get(
    "SOCIALS_IMAGES_PROMPT_PATH",
    "/home/GOD/gnosys-plugin-v2/doc-mirror-system/plugin/skills/doc-mirror-prompts/"
    "resources/prompts/skill2framework/socials-organ/socials-images-from-pack/SKILL.md",
)
RENDER_SCRIPT = os.environ.get(
    "EXCALIDRAW_RENDER_SCRIPT",
    "/tmp/heaven_data/skills/excalidraw-render/scripts/render.py",
)
EXPECTED_PNGS = ("hero.png", "social-share.png", "thumbnail.png")


def build_prompt(pack_path: str, blog_md_path: str, out_dir: str) -> str:
    raw = Path(DEFAULT_PROMPT_PATH).read_text()
    marker = "## PROMPT"
    body = raw.split(marker, 1)[1] if marker in raw else raw
    return (body.replace("{pack_path}", pack_path)
                .replace("{blog_md_path}", blog_md_path)
                .replace("{out_dir}", out_dir)
                .replace("{render_script}", RENDER_SCRIPT))


def run_claude_agent(prompt: str, timeout: int = 900) -> Dict[str, Any]:
    """claude -p dispatch (same pattern as cave's coglog publisher _run_agent).
    Returns {ok, error}; never raises."""
    # claude -p must run on the claude.ai login (the coglog pattern) — a
    # provider key in the caller's env (e.g. a sourced system_config for the
    # heaven/minimax legs) would take precedence and break it (proven
    # 2026-07-10: rc=1 "connectors are disabled ... auth source is set").
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("ANTHROPIC_")}
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Read,Write,Bash"],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        if proc.returncode != 0:
            logger.error("claude -p failed rc=%d: %s", proc.returncode,
                         proc.stderr[:500])
            return {"ok": False,
                    "error": f"claude -p rc={proc.returncode}: {proc.stderr[:200]}"}
        return {"ok": True, "error": ""}
    except subprocess.TimeoutExpired:
        logger.error("claude -p timed out after %ds", timeout)
        return {"ok": False, "error": f"claude -p timed out after {timeout}s"}
    except OSError as e:
        logger.error("claude -p not runnable: %s", e, exc_info=True)
        return {"ok": False, "error": f"claude -p not runnable: {e}"}


def render_for_pack(pack_path: str, blog_md_path: str,
                    out_dir: str | None = None) -> Dict[str, Any]:
    """Render one pack's images; verify the PNG artifacts. Returns a status dict."""
    if Path(pack_path).is_dir():
        # Operators pass the per-slug queue DIR as often as the pack.md itself;
        # a bare dir would silently derive the wrong images dir (its parent).
        pack_path = str(Path(pack_path) / "pack.md")
    if not Path(pack_path).exists():
        return {"status": "failed", "error": f"pack not found: {pack_path}",
                "images_dir": ""}
    out = Path(out_dir) if out_dir else Path(pack_path).parent / "images"
    out.mkdir(parents=True, exist_ok=True)

    prompt = build_prompt(pack_path, blog_md_path, str(out))
    logger.info("unicorn images: dispatching renderer for %s", out)
    res = run_claude_agent(prompt)

    missing = [n for n in EXPECTED_PNGS if not (out / n).exists()]
    if not res["ok"] or missing:
        error = res["error"] or f"agent finished but missing: {', '.join(missing)}"
        logger.error("unicorn images: failed — %s", error)
        return {"status": "failed", "error": error[:300], "images_dir": str(out)}

    logger.info("unicorn images: rendered %s", ", ".join(EXPECTED_PNGS))
    return {"status": "rendered", "images_dir": str(out),
            "images": [str(out / n) for n in EXPECTED_PNGS]}


def _packed_without_images(graph) -> List[Dict[str, Any]]:
    rows = graph.execute_query(
        "MATCH (c:Wiki) WHERE c.socials_packed = true "
        "AND c.socials_pack_path IS NOT NULL AND c.images_rendered IS NULL "
        "RETURN c.n AS n, properties(c) AS p LIMIT 25",
        {},
    )
    return [{"concept": r.get("n"), "props": dict(r.get("p") or {})}
            for r in rows or [] if r.get("n")]


def fire_socials_images(**kwargs: Any) -> Dict[str, Any]:
    """CronAutomation code_pointer — render images for socials packs."""
    if kwargs.get("pack_path"):
        return render_for_pack(kwargs["pack_path"],
                               kwargs.get("blog_md_path", ""),
                               kwargs.get("out_dir"))

    graph, set_props, _q = _carton()
    if graph is None:
        return {"status": "no_connection"}

    pending = _packed_without_images(graph)
    if not pending:
        return {"status": "no_pending"}

    results: List[Dict[str, Any]] = []
    for item in pending:
        concept, props = item["concept"], item["props"]
        md = props.get("output_path") or props.get("output_md_path") or ""
        report = render_for_pack(props["socials_pack_path"], md)
        if report["status"] == "rendered":
            set_props(concept,
                      {"images_rendered": True, "images_dir": report["images_dir"],
                       "images_rendered_at": datetime.now().isoformat()},
                      mode="merge", shared_connection=graph)
        else:
            set_props(concept, {"images_error": report["error"][:200]},
                      mode="merge", shared_connection=graph)
        results.append({"concept": concept, **report})

    rendered = sum(1 for r in results if r["status"] == "rendered")
    return {"status": "done", "rendered": rendered,
            "failed": len(results) - rendered, "results": results}
