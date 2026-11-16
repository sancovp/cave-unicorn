"""fire_site_publish — the UNICORN automation entrypoint (CronAutomation code_pointer).

Two modes:
  - direct:  fire_site_publish(md_path=...) publishes ONE markdown file (CLI path).
  - scan:    fire_site_publish() queries CartON for Blog_Request nodes the blog
    organ already completed ({status: "done"}) that have NOT been site-published
    (no ``site_published`` property), publishes each done blog's output markdown
    onto the live site, and flips ``site_published``/``site_url``/
    ``site_published_at`` onto the node.

Same never-raises contract as cave.core.publishing.blog_organ_nightly: failures
are captured in the return dict (and, in scan mode, on the node), never thrown —
this runs on the Heart tick.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import update_wire
from .announce import announce_posts
from .config import load_config
from .crosslink import chapter_nav_links, kind_of, render_chapter_nav
from .overviews import regenerate_overviews
from .site import publish_file, publish_funnel_file

logger = logging.getLogger(__name__)


def _carton():
    """CartON property primitives + shared connection (import-if-present).

    Same pattern as cave.core.publishing.blog_organ_nightly._carton — carton_mcp
    is the canonical home of the property primitives. Returns
    (graph, set_props_fn, query_fn) or (None, None, None).
    """
    try:
        from carton_mcp.add_concept_tool import _get_module_connection
        from carton_mcp.carton_utils import (
            set_concept_properties,
            query_concepts_by_properties,
        )
    except ImportError as e:
        logger.error("carton_mcp not importable: %s", e, exc_info=True)
        return None, None, None
    graph = _get_module_connection()
    if graph is None:
        logger.error("no neo4j connection available (check NEO4J_* env vars)")
        return None, None, None
    return graph, set_concept_properties, query_concepts_by_properties


def _read_props(graph, concept_name: str) -> Optional[Dict[str, Any]]:
    rows = graph.execute_query(
        "MATCH (c:Wiki {n: $n}) RETURN properties(c) AS p LIMIT 1",
        {"n": concept_name},
    )
    if not rows:
        return None
    return dict(rows[0].get("p") or {})


def _unpublished_done_blogs(query_fn, graph) -> List[Dict[str, Any]]:
    """Blog_Request-shaped nodes with status=done that carry an output markdown
    path but no site_published flag.

    Filters on the output-path property IN the cypher (not a two-step
    status-then-filter): the ``status`` property lane is shared with doc-mirror
    (dozens of unrelated status=done journal nodes), so a bare status query
    would crowd real blogs out of the LIMIT window. ``query_fn`` is unused but
    kept in the signature so the CLI/_carton wiring stays uniform.

    THE SHAPE GUARD (2026-07-20): the scan publishes ONLY nodes that are
    actually IS_A Blog_Request (the contract this docstring always stated but
    the cypher never enforced), OR nodes explicitly opted in with
    ``site_publish_ready = true`` — the publish-everything lane, stamped only
    by the certified render pipeline (nothing stamps it yet; auto-flow of
    manuals rides AFTER the PR-4 voice-pass ratifies the render voice).
    Without this gate, ANY graph node that gained status=done + output_path
    (e.g. a manual spec) would be pushed to the live site unreviewed.
    """
    del query_fn  # precision requires direct cypher; see docstring
    rows = graph.execute_query(
        "MATCH (c:Wiki) WHERE c.status = 'done' "
        "AND (c.output_path IS NOT NULL OR c.output_md_path IS NOT NULL) "
        "AND c.site_published IS NULL "
        "AND (EXISTS { (c)-[:IS_A]->(:Wiki {n: 'Blog_Request'}) } "
        "     OR c.site_publish_ready = true) "
        "RETURN c.n AS n, properties(c) AS p LIMIT 100",
        {},
    )
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        name, props = row.get("n"), dict(row.get("p") or {})
        if not name:
            continue
        md = props.get("output_path") or props.get("output_md_path")
        out.append({"concept": name, "md_path": md, "props": props})
    return out


def funnel_slug_of(concept: str) -> str:
    """The site slug of a Site_Publish_<Framework>_Funnel node. PURE.
    'Site_Publish_Grand_Argument_Synthesis_Gas_Funnel' -> 'grand-argument-synthesis-gas'."""
    name = concept
    if name.startswith("Site_Publish_"):
        name = name[len("Site_Publish_"):]
    if name.endswith("_Funnel"):
        name = name[: -len("_Funnel")]
    return name.lower().replace("_", "-")


def _chapter_nav_for(graph, concept: str, props: Dict[str, Any]) -> str:
    """Compute the chapter cross-link HTML block for a Site_Publish node. THIN I/O.

    Reads the KIND off the node name (Story/Usage), finds the sibling node (the
    opposite kind of the SAME framework) for its site_url, and the framework's
    ``funnel_cta_url``/``funnel_cta_label`` (the funnel page it points to). Delegates
    the actual link computation + HTML render to the PURE crosslink functions. A node
    with no chapter kind, or with no sibling/funnel data, yields fewer links or "" —
    never an error, never an invented link. The funnel URL source is the framework
    node's funnel_cta_url; if none exists on the graph yet, the funnel link is absent.
    """
    kind = kind_of(concept)
    if kind is None:
        return ""
    if kind == "story":
        sibling = concept[: -len("_Story_Blog")] + "_Usage_Blog"
    else:
        sibling = concept[: -len("_Usage_Blog")] + "_Story_Blog"
    sibling_props = _read_props(graph, sibling) or {}

    funnel_url = None
    funnel_label = "Join Sanctuary Revolution"
    rows = graph.execute_query(
        "MATCH (c:Wiki {n: $n})-[:PART_OF]->(f:Wiki) "
        "WHERE f.funnel_cta_url IS NOT NULL "
        "RETURN f.funnel_cta_url AS url, f.funnel_cta_label AS label LIMIT 1",
        {"n": concept},
    )
    if rows:
        funnel_url = rows[0].get("url")
        if rows[0].get("label"):
            funnel_label = rows[0].get("label")

    links = chapter_nav_links({**props, "concept": concept},
                              sibling_props, funnel_url, funnel_label)
    return render_chapter_nav(links)


def fire_site_publish(**kwargs: Any) -> Dict[str, Any]:
    """CronAutomation code_pointer — publish done-but-unpublished blogs to the site.

    kwargs (all optional): md_path (direct single-file mode), slug, tags (list),
    month, push (bool — overrides config), config_path.
    """
    try:
        cfg = load_config(kwargs.get("config_path"))
    except (FileNotFoundError, KeyError) as e:
        logger.error("unicorn: %s", e)
        return {"status": "no_config", "error": str(e)}

    push = kwargs.get("push")

    # Direct mode — the CLI/manual path.
    if kwargs.get("md_path"):
        try:
            report = publish_file(
                kwargs["md_path"], cfg,
                slug=kwargs.get("slug"), tags=kwargs.get("tags"),
                month=kwargs.get("month"), push=push,
                title=kwargs.get("title"), hook=kwargs.get("hook"),
                link_map=kwargs.get("link_map"),
            )
            if report.get("pushed"):
                report["announce"] = announce_posts([report], cfg)
            return report
        except Exception as e:
            logger.error("unicorn: direct publish failed: %s", e, exc_info=True)
            return {"status": "failed", "md_path": kwargs["md_path"], "error": str(e)[:300]}

    # Scan mode — CartON Blog_Request nodes done but not site-published.
    graph, set_props, query_props = _carton()
    if graph is None:
        return {"status": "no_connection"}

    pending = _unpublished_done_blogs(query_props, graph)
    if not pending:
        return {"status": "no_pending"}

    results: List[Dict[str, Any]] = []
    for item in pending:
        concept, md_path = item["concept"], item["md_path"]
        try:
            # THE KIND ROUTE (2026-07-20): site_publish_kind='funnel' nodes are
            # RENDERED FULL PAGES (render_funnel output) — they ship via the
            # root-level funnel lane; everything else is a blog md riding the
            # skeleton pipe. One contract, two repos: the kind property is
            # stamped by manualcore (funnel_publish_payload) — change both
            # sides together.
            if (item.get("props") or {}).get("site_publish_kind") == "funnel":
                report = publish_funnel_file(
                    md_path, cfg, slug=funnel_slug_of(concept), push=push)
            else:
                chapter_nav = _chapter_nav_for(graph, concept, item.get("props") or {})
                report = publish_file(md_path, cfg, push=push,
                                      chapter_nav_html=chapter_nav)
            set_props(
                concept,
                {"site_published": True,
                 "site_url": report["live_url"],
                 "site_published_at": datetime.now().isoformat()},
                mode="merge", shared_connection=graph,
            )
            result = {"concept": concept, **report}
            # THE UPDATE WIRE — blast the "{actor} just published {thing} at {link}"
            # line to the membership #updates stream. Its own try: the SACRED-guild
            # gate RAISES (a hard refusal) and a notify failure must NOT fail the
            # publish (which already landed) — so a refusal/failure is logged loudly
            # and recorded on the result, never un-publishing the blog.
            try:
                result["update_wire"] = update_wire.notify_publish(report, cfg)
            except Exception as we:
                logger.error("unicorn: update wire refused/failed for %s: %s",
                             concept, we, exc_info=True)
                result["update_wire"] = {"status": "refused", "error": str(we)[:200]}
            results.append(result)
            logger.info("unicorn: %s -> %s", concept, report["live_url"])
        except Exception as e:
            logger.error("unicorn: publish failed for %s: %s", concept, e, exc_info=True)
            set_props(
                concept,
                {"site_publish_error": str(e)[:200]},
                mode="merge", shared_connection=graph,
            )
            results.append({"concept": concept, "status": "failed", "error": str(e)[:200]})

    published = sum(1 for r in results if r.get("status") in ("published", "staged"))
    announce = announce_posts([r for r in results if r.get("pushed")], cfg)
    # Regenerate the per-facet overview pages from graph state (idempotent; writes
    # files only, never commits/pushes). A failure here never fails the publish run.
    try:
        overviews = regenerate_overviews(cfg, graph=graph)
    except Exception as e:
        logger.error("unicorn: overview regeneration failed: %s", e, exc_info=True)
        overviews = {"status": "failed", "error": str(e)[:200]}
    return {"status": "done", "published": published,
            "failed": len(results) - published, "results": results,
            "announce": announce, "overviews": overviews}
