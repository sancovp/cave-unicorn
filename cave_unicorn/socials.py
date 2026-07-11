"""fire_socials_pack — the socials leg (CronAutomation code_pointer).

Scan: CartON nodes with ``site_published: true`` and no ``socials_packed`` →
FRAMEWORK-FIRST GATE (a node whose persisted sibling core lacks
``deep_dive_url``/``plugin_url`` is marked ``framework_missing`` and skipped —
never packed linkless; it retries on later scans once the chapter step wires
the links) → for each ready node, dispatch the blog-writing agent
(heaven/minimax, BashTool — fills journey_core.json + journey_blog.json against
the live contract) → render the suite deterministically → verify the artifacts
→ flip ``socials_packed``/``socials_pack_path`` (or ``socials_pack_error``).

Direct mode: fire_socials_pack(md_path=..., live_url=..., slug=...) packs one
blog without touching CartON (the CLI path). Direct mode BYPASSES the
framework gate deliberately — it is the operator's explicit hand.

The pack lands at $HEAVEN_DATA_DIR/socials_queue/{slug}/pack.md — the
ready-to-post queue Isaac reads ("a pipeline that gives me images and posts").
Same never-raises contract as the other fire_* automations.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dispatch import run_agent
from .publish import _carton

logger = logging.getLogger(__name__)

# Canonical home of THE blog-writing skill (Isaac 2026-07-10: "give the agents
# the right instructions... make that a skill... thats the blog writing skill...
# then give it to that agent"): the agent fills journey_core.json +
# journey_blog.json + image-prompts.md against the live field contract; this
# module then renders the AIDA blog + the from_core socials DETERMINISTICALLY
# (journey_suite). Supersedes the freestyle socials-pack-from-blog prompt.
DEFAULT_PROMPT_PATH = os.environ.get(
    "SOCIALS_ORGAN_PROMPT_PATH",
    "/home/GOD/gnosys-plugin-v2/doc-mirror-system/plugin/skills/doc-mirror-prompts/"
    "resources/prompts/skill2framework/blog-organ/blog-writing/SKILL.md",
)


def _queue_dir() -> Path:
    return Path(os.environ.get("HEAVEN_DATA_DIR", "/tmp/heaven_data")) / "socials_queue"


def build_prompt(blog_md_path: str, live_url: str, slug: str, out_dir: str,
                 journey_source: str = "",
                 existing_core: str = "none") -> str:
    """Fill the blog-writing prompt body with this journey's specifics.

    ``journey_source`` = the DEEP record paths (the Blog_Request's
    journey_source property — the journal/spec the blog was derived from), so
    the agent reaches into the raw material, not just the rendered derivative.
    ``existing_core`` = a persisted journey_core.json to REUSE (fill once).
    """
    raw = Path(DEFAULT_PROMPT_PATH).read_text()
    marker = "## PROMPT"
    body = raw.split(marker, 1)[1] if marker in raw else raw
    return (body.replace("{blog_md_path}", blog_md_path)
                .replace("{live_url}", live_url)
                .replace("{slug}", slug)
                .replace("{out_dir}", out_dir)
                .replace("{journey_source}", journey_source or "")
                .replace("{existing_core}", existing_core or "none"))


def _sibling_core(md_path: str) -> str:
    """The core the blog organ persists next to its output md, if present."""
    if not md_path:
        return "none"
    candidate = Path(md_path.rsplit(".", 1)[0] + ".journey_core.json")
    return str(candidate) if candidate.exists() else "none"


def _framework_ready(sibling_core_path: str) -> bool:
    """Framework-first gate (Isaac 2026-07-10, the archival-law fix queue):
    the socials organ must NOT write a blog whose CTA/demo sections have no
    real links to point at. ``deep_dive_url`` is the true completeness
    signal — the narrative-blog-from-aios prompt fills ``plugin_url`` at
    blog-organ time (it is derived from the always-REQUIRED
    ``plugin_repo_url``) but its own comment says deep_dive_url is
    optional-at-fill-time: "the chapter step wires them later". So a journey
    is framework-ready only once that later wiring has happened — checked by
    reading the SAME persisted sibling core the blog-writing agent would
    reuse, never re-derived here. No sibling core at all -> not ready (can't
    verify without one)."""
    if not sibling_core_path or sibling_core_path == "none":
        return False
    try:
        core = json.loads(Path(sibling_core_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("framework-ready check: unreadable core %s: %s",
                     sibling_core_path, e, exc_info=True)
        return False
    return bool(core.get("deep_dive_url")) and bool(core.get("plugin_url"))


def _unpacked_published(graph) -> List[Dict[str, Any]]:
    """site_published nodes with an output md that have no socials pack yet."""
    rows = graph.execute_query(
        "MATCH (c:Wiki) WHERE c.site_published = true "
        "AND (c.output_path IS NOT NULL OR c.output_md_path IS NOT NULL) "
        "AND c.socials_packed IS NULL "
        "RETURN c.n AS n, properties(c) AS p LIMIT 50",
        {},
    )
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        name, props = row.get("n"), dict(row.get("p") or {})
        if name:
            out.append({"concept": name, "props": props})
    return out


def _enforce_canonical_core(core_json: Path, canonical: str,
                            live_url: str) -> None:
    """FILL-ONCE ENFORCED BY CODE (live-found 2026-07-11): the release-scan
    run's agent RETYPED the existing core from memory instead of copying it,
    corrupting nine fields (plah/IKZ/sancopv — a broken URL). A prompt cannot
    guarantee byte-fidelity, so when a canonical core exists the MODULE is
    the authority: overwrite whatever the agent wrote with the canonical
    content before the deterministic render. The only sanctioned addition is
    blog_url = live_url when the canonical core leaves it unset (PASS 2's
    own rule, done mechanically). The canonical FILE is never written."""
    canon = json.loads(Path(canonical).read_text())
    if not canon.get("blog_url") and live_url:
        canon["blog_url"] = live_url
    if core_json.exists() and json.loads(core_json.read_text()) != canon:
        logger.warning("unicorn socials: agent-written core differed from "
                       "canonical %s — canonical enforced", canonical)
    core_json.write_text(json.dumps(canon, indent=2) + "\n")


def pack_one(md_path: str, live_url: str, slug: str,
             journey_source: str = "",
             existing_core: str = "") -> Dict[str, Any]:
    """Dispatch the blog-writing agent (fills journey_core.json +
    journey_blog.json + image-prompts.md), then render the suite
    DETERMINISTICALLY module-side (the agent's own render run is only its
    self-correction loop — this module is the authority). Never raises."""
    out_dir = _queue_dir() / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    canonical = existing_core or _sibling_core(md_path)

    try:
        prompt = build_prompt(md_path, live_url, slug, str(out_dir),
                              journey_source=journey_source,
                              existing_core=canonical)
    except OSError as e:
        logger.error("socials prompt build failed: %s", e, exc_info=True)
        return {"status": "failed", "error": f"prompt build failed: {e}"}

    logger.info("unicorn socials: dispatching blog-writing agent for %s", slug)
    ok, err, model = run_agent(prompt, name="unicorn_socials")

    # The agent's claim is not the artifact — the fills must exist.
    core_json = out_dir / "journey_core.json"
    blog_json = out_dir / "journey_blog.json"
    missing = [p.name for p in (core_json, blog_json) if not p.exists()]
    if not ok or missing:
        error = err or f"agent reported ok but fills missing: {', '.join(missing)}"
        logger.error("unicorn socials: %s failed — %s", slug, error)
        return {"status": "failed", "error": error[:300], "model": model}

    if canonical and canonical != "none":
        try:
            _enforce_canonical_core(core_json, canonical, live_url)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("unicorn socials: canonical-core enforcement failed "
                         "for %s: %s", slug, e, exc_info=True)
            return {"status": "failed", "model": model,
                    "error": f"canonical core enforcement failed: {e}"[:300]}

    return _render_pack(out_dir, slug, model)


def _render_pack(out_dir: Path, slug: str, model: str) -> Dict[str, Any]:
    """Deterministic suite render (validates the fills; an invalid fill or
    render failure is captured as a failed dict, never raised)."""
    try:
        from .journey_suite import render_suite
        image_prompts = out_dir / "image-prompts.md"
        report = render_suite(str(out_dir / "journey_core.json"),
                              str(out_dir / "journey_blog.json"), str(out_dir),
                              str(image_prompts) if image_prompts.exists() else None)
    except Exception as e:
        logger.error("unicorn socials: suite render failed for %s: %s", slug, e,
                     exc_info=True)
        return {"status": "failed", "error": f"suite render failed: {e}"[:300],
                "model": model}

    logger.info("unicorn socials: %s -> %s", slug, report["pack"])
    return {"status": "packed", "slug": slug, "model": model,
            "pack_path": report["pack"], "blog_aida": report["blog_aida"],
            "core_path": report["core"]}


def _slug_from(props: Dict[str, Any], concept: str) -> str:
    url = props.get("site_url", "")
    if url.endswith(".html"):
        return url.rsplit("/", 1)[-1][:-5]
    return concept.lower()


def fire_socials_pack(**kwargs: Any) -> Dict[str, Any]:
    """CronAutomation code_pointer — generate socials packs for live blogs.

    kwargs (direct mode): md_path + live_url (+ slug). Scan mode: no kwargs.
    """
    if kwargs.get("md_path"):
        slug = kwargs.get("slug") or Path(kwargs["md_path"]).stem
        return pack_one(kwargs["md_path"], kwargs.get("live_url", ""), slug,
                        journey_source=kwargs.get("journey_source", ""),
                        existing_core=kwargs.get("existing_core", ""))

    graph, set_props, _query = _carton()
    if graph is None:
        return {"status": "no_connection"}

    pending = _unpacked_published(graph)
    if not pending:
        return {"status": "no_pending"}

    results: List[Dict[str, Any]] = []
    for item in pending:
        concept, props = item["concept"], item["props"]
        md = props.get("output_path") or props.get("output_md_path")
        slug = _slug_from(props, concept)

        # Framework-first gate (Isaac 2026-07-10 archival-law fix queue item 1):
        # never dispatch on a journey whose framework package (deep-dive
        # chapter + plugin) isn't live yet — that is what produced a blog
        # with "no links from the framework". No socials_packed flip here,
        # so this node is picked up again on the next scan once the chapter
        # step wires deep_dive_url onto the sibling core.
        if not _framework_ready(_sibling_core(md)):
            set_props(concept, {"framework_missing": True},
                      mode="merge", shared_connection=graph)
            results.append({"concept": concept, "status": "framework_missing",
                            "error": "no deep_dive_url/plugin_url on the "
                                     "persisted core yet — queued for the "
                                     "chapter pipeline"})
            continue

        report = pack_one(md, props.get("site_url", ""), slug,
                          journey_source=str(props.get("journey_source", "")))
        if report["status"] == "packed":
            flip = {"socials_packed": True,
                    "socials_pack_path": report["pack_path"],
                    "socials_packed_at": datetime.now().isoformat()}
            if props.get("framework_missing"):
                # The gate held this node on an earlier scan; the framework
                # has since been wired — clear the stale flag with the flip.
                flip["framework_missing"] = False
            if props.get("socials_pack_error"):
                # An earlier attempt failed and left its error on the node;
                # a healthy packed node must not carry a stale error string.
                flip["socials_pack_error"] = ""
            set_props(concept, flip, mode="merge", shared_connection=graph)
        else:
            set_props(concept, {"socials_pack_error": report["error"][:200]},
                      mode="merge", shared_connection=graph)
        results.append({"concept": concept, **report})

    packed = sum(1 for r in results if r["status"] == "packed")
    return {"status": "done", "packed": packed,
            "failed": len(results) - packed, "results": results}
