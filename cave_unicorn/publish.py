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

from .announce import announce_posts
from .config import load_config
from .site import publish_file

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
    """
    del query_fn  # precision requires direct cypher; see docstring
    rows = graph.execute_query(
        "MATCH (c:Wiki) WHERE c.status = 'done' "
        "AND (c.output_path IS NOT NULL OR c.output_md_path IS NOT NULL) "
        "AND c.site_published IS NULL "
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
            report = publish_file(md_path, cfg, push=push)
            set_props(
                concept,
                {"site_published": True,
                 "site_url": report["live_url"],
                 "site_published_at": datetime.now().isoformat()},
                mode="merge", shared_connection=graph,
            )
            results.append({"concept": concept, **report})
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
    return {"status": "done", "published": published,
            "failed": len(results) - published, "results": results,
            "announce": announce}
