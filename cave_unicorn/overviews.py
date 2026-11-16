"""Per-facet overview pages — the website content web (deliverable B).

Isaac's design (verbatim): "there is an overview, this never changes and links to
journeys and frameworks. Journeys is about each journey, links to every blog post
(it's a notifier about new blogs being added), and frameworks links to the deeper
blog post (the 2nd blog post in each manual publishing event) and links back to the
funnel." And: "the update system IS the website not the discord" — so the content web
lives HERE, on the site, not in Discord.

One overview page per facet (paiab / sanctum / cave / starsystem):
  - a never-changing intro frame (connective tissue — no income claims, no invented copy),
  - a JOURNEYS section: every published blog post, newest first = the "new blogs" notifier,
  - a FRAMEWORKS section: each manual, linking its deeper (usage) blog + the funnel.

FACET CLASSIFICATION (two layers): an explicit ``facet`` property on the framework node
(set via set_properties — the markup surface, same pattern as the funnel_* fills) WINS
when it names a real facet; otherwise the honest v0 heuristic places the framework by
matching its ``part_of``/``tags`` names against the facet keywords
(sanctum/cave/starsystem/paiab, in that order); anything that matches none falls to the
single default facet ``paiab``. It is NEVER guessed silently per-post — every post inherits
its framework's classification. (The override exists because part_of edges can be
composition-session residue, not facet statements — proven by Grand_Argument_Synthesis_Gas
riding a PART_OF Sanctum_Rituals edge into the sanctum facet, 2026-07-20.)

v0 TITLES (honest): journey titles are DERIVED from the framework name + the post kind,
mirroring render_blog.py's default titles ("<Name>: The Story" / "Run <Name> Yourself") —
which is exactly what the live pages carry. A future version could read the post's own <h1>.

PURE CORE (no I/O): facet_of, journey_title, group_by_facet, facet_overview.
THIN I/O: regenerate_overviews (queries the graph, writes facets/<facet>.html into the
site checkout, idempotent — re-renders in place; never commits/pushes).
"""

from __future__ import annotations

import html as _html
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# The four facets. Order is the classification precedence (paiab is also the default).
FACETS: Tuple[str, ...] = ("sanctum", "cave", "starsystem", "paiab")
DEFAULT_FACET = "paiab"

FACET_DISPLAY: Dict[str, str] = {
    "paiab": "PAIAB", "sanctum": "SANCTUM", "cave": "CAVE", "starsystem": "STARSYSTEM",
}
# The never-changing intro frame per facet — factual descriptors from the site's own
# domain architecture (.claude/CLAUDE.md), connective tissue only, no income claims.
FACET_INTRO: Dict[str, str] = {
    "paiab": "Building agents. The journeys and frameworks behind PAIAB — each one composed "
             "from work that was actually done and proven.",
    "sanctum": "Life architecture. The journeys and frameworks behind SANCTUM — each one "
               "composed from work that was actually done and proven.",
    "cave": "Business automation. The journeys and frameworks behind CAVE — each one composed "
            "from work that was actually done and proven.",
    "starsystem": "Development workflow. The journeys and frameworks behind STARSYSTEM — each "
                  "one composed from work that was actually done and proven.",
}


def facet_of(part_of: Optional[List[str]], tags: Optional[List[str]] = None) -> str:
    """Classify a framework to a facet from its ``part_of``/``tags`` names. PURE.

    Matches the facet keywords (sanctum/cave/starsystem/paiab, in precedence order)
    as case-insensitive substrings of the joined part_of + tags names; the first
    match wins, and anything matching none falls to the default facet ``paiab``.
    """
    hay = " ".join(list(part_of or []) + list(tags or [])).lower()
    for facet in FACETS:
        if facet in hay:
            return facet
    return DEFAULT_FACET


def _humanize(framework: str) -> str:
    """Framework concept name -> a display title ('Grand_Argument_Synthesis_Gas' ->
    'Grand Argument Synthesis Gas'), matching render_blog.py's _nice_title output."""
    return framework.replace("_", " ").title()


def journey_title(node_name: str, framework: str) -> str:
    """Derive a blog post's display title from its Site_Publish node name + framework. PURE.

    Mirrors render_blog.py's default titles (what the live pages actually carry):
    a ``*_Usage_Blog`` -> 'Run <Name> Yourself'; a ``*_Story_Blog`` -> '<Name>: The Story';
    anything else -> the humanized framework name.
    """
    nice = _humanize(framework)
    if node_name.endswith("_Usage_Blog"):
        return f"Run {nice} Yourself"
    if node_name.endswith("_Story_Blog"):
        return f"{nice}: The Story"
    return nice


def group_by_facet(
    rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Group published-blog rows into per-facet journeys + frameworks. PURE.

    Each row: {node, site_url, published_at, framework, funnel_url, funnel_label,
    framework_part_of, framework_tags, framework_facet}. Returns
    {facet: {"journeys": [...], "frameworks": [...]}}.
    Journeys = one entry per published post (newest first). Frameworks = one entry per
    framework, carrying its USAGE (deeper) blog url + funnel — the framework card the
    design links "to the deeper blog post ... and back to the funnel".

    Facet: an explicit ``framework_facet`` naming a real facet WINS (the framework
    node's ``facet`` property — the markup override); anything else (absent, or not a
    real facet name) falls through to the facet_of heuristic.
    """
    journeys: Dict[str, List[Dict[str, str]]] = {}
    fw_acc: Dict[str, Dict[str, Dict[str, Any]]] = {}  # facet -> framework -> data
    for row in rows:
        node = str(row.get("node", ""))
        site_url = row.get("site_url")
        framework = str(row.get("framework", ""))
        if not node or not site_url or not framework:
            continue
        explicit = str(row.get("framework_facet") or "").lower()
        facet = explicit if explicit in FACETS else \
            facet_of(row.get("framework_part_of"), row.get("framework_tags"))
        journeys.setdefault(facet, []).append({
            "title": journey_title(node, framework),
            "url": str(site_url),
            "date": str(row.get("published_at") or ""),
        })
        fw = fw_acc.setdefault(facet, {}).setdefault(framework, {
            "name": framework,
            "title": _humanize(framework),
            "usage_url": None,
            "funnel_url": row.get("funnel_url"),
            "funnel_label": row.get("funnel_label") or "Join Sanctuary Revolution",
        })
        if node.endswith("_Usage_Blog"):
            fw["usage_url"] = str(site_url)

    out: Dict[str, Dict[str, Any]] = {}
    for facet in set(list(journeys) + list(fw_acc)):
        j = sorted(journeys.get(facet, []), key=lambda d: d["date"], reverse=True)
        frameworks = sorted(fw_acc.get(facet, {}).values(), key=lambda d: d["title"])
        out[facet] = {"journeys": j, "frameworks": frameworks}
    return out


def _journey_card(journey: Dict[str, str]) -> str:
    url = _html.escape(str(journey.get("url", "")), quote=True)
    title = _html.escape(str(journey.get("title", "")))
    date = _html.escape(str(journey.get("date", ""))[:10])  # YYYY-MM-DD only
    date_p = f"<p>{date}</p>" if date else ""
    return (f'      <a href="{url}" class="blog-card"><h3>{title}</h3>{date_p}'
            f'<span class="read-link">Read &rarr;</span></a>')


def _framework_card(framework: Dict[str, Any]) -> str:
    title = _html.escape(str(framework.get("title", "")))
    actions: List[str] = []
    usage_url = framework.get("usage_url")
    if usage_url:
        actions.append(
            f'        <a href="{_html.escape(str(usage_url), quote=True)}" '
            f'class="blog-cta-primary">Run it yourself &rarr;</a>')
    funnel_url = framework.get("funnel_url")
    if funnel_url:
        label = _html.escape(str(framework.get("funnel_label") or "Join Sanctuary Revolution"))
        actions.append(
            f'        <a href="{_html.escape(str(funnel_url), quote=True)}" '
            f'class="blog-cta-secondary">{label} &rarr;</a>')
    actions_html = ("\n      <div class=\"blog-cta-actions\">\n"
                    + "\n".join(actions) + "\n      </div>") if actions else ""
    return (f'      <div class="blog-card"><h3>{title}</h3>{actions_html}\n      </div>')


def facet_overview(facet: str, journeys: List[Dict[str, str]],
                   frameworks: List[Dict[str, Any]]) -> str:
    """Render one facet's overview page HTML. PURE.

    A full page in the site's blog-style.css chrome (#isaac-site wrapper, so it inherits
    site-header/section-tag/blog-grid/blog-card/blog-cta vocabulary). The never-changing
    intro frame + a JOURNEYS grid (blog posts, newest-first) + a FRAMEWORKS grid (each
    manual linking its usage blog + funnel). Blog/funnel links are the graph's ABSOLUTE
    site_urls; chrome links are relative (the page lives at facets/<facet>.html).
    """
    display = FACET_DISPLAY.get(facet, facet.upper())
    intro = FACET_INTRO.get(facet, f"The journeys and frameworks behind {display}.")
    journey_cards = "\n".join(_journey_card(j) for j in journeys) or \
        '      <p style="color:var(--text-3);">No posts yet.</p>'
    framework_cards = "\n".join(_framework_card(f) for f in frameworks)
    frameworks_section = ""
    if frameworks:
        frameworks_section = (
            '\n    <div class="section-tag" style="margin-top:4rem;">Frameworks</div>\n'
            '    <h2>The manuals</h2>\n'
            '    <p class="post-subtitle">Each manual links its deeper usage post and the funnel.</p>\n'
            '    <div class="blog-grid">\n'
            f'{framework_cards}\n'
            '    </div>\n')
    return f"""<link rel="stylesheet" href="../blog/blog-style.css">
<div id="isaac-site">
  <div class="site-header">
    <a href="../index.html" class="logo">Isaac — TWI</a>
    <div class="nav-links">
      <a href="../blog/" class="nav-link">Blog</a>
      <a href="../frameworks.html" class="nav-link">Frameworks</a>
      <a href="../apply.html" class="nav-cta">Book a Call</a>
    </div>
  </div>

  <article>
    <div class="post-tag">{_html.escape(display)} — Overview</div>
    <h1>{_html.escape(display)}</h1>
    <p class="post-subtitle">{_html.escape(intro)}</p>

    <div class="section-tag">Journeys</div>
    <h2>Every post, newest first</h2>
    <p class="post-subtitle">The notifier for new blogs as they are added.</p>
    <div class="blog-grid">
{journey_cards}
    </div>
{frameworks_section}  </article>

  <div class="site-footer">
    <span>&copy; 2026 Isaac &mdash; TWI Consulting</span>
    <span><a href="../index.html" style="color:var(--amber);text-decoration:none;">&larr; Home</a></span>
  </div>
</div>
<script src="../sticky-cta.js"></script>
<script src="../newsletter.js"></script>
"""


# ═══════════════════════════════════════════════════════════════════════════
# THIN I/O
# ═══════════════════════════════════════════════════════════════════════════

def _query_published_blogs(graph) -> List[Dict[str, Any]]:
    """Query the graph for every site_published Story/Usage blog node + its framework's
    funnel + classification. THIN I/O. Returns row dicts group_by_facet eats."""
    rows = graph.execute_query(
        "MATCH (n:Wiki)-[:PART_OF]->(f:Wiki) "
        "WHERE (n.n ENDS WITH '_Story_Blog' OR n.n ENDS WITH '_Usage_Blog') "
        "AND n.site_published = true AND n.site_url IS NOT NULL "
        "OPTIONAL MATCH (f)-[:PART_OF]->(fp:Wiki) "
        "RETURN n.n AS node, n.site_url AS site_url, "
        "toString(n.site_published_at) AS published_at, f.n AS framework, "
        "f.funnel_cta_url AS funnel_url, f.funnel_cta_label AS funnel_label, "
        "f.facet AS framework_facet, "
        "collect(DISTINCT fp.n) AS framework_part_of",
        {},
    )
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        out.append({
            "node": row.get("node"),
            "site_url": row.get("site_url"),
            "published_at": row.get("published_at"),
            "framework": row.get("framework"),
            "funnel_url": row.get("funnel_url"),
            "funnel_label": row.get("funnel_label"),
            "framework_facet": row.get("framework_facet"),
            "framework_part_of": row.get("framework_part_of") or [],
            "framework_tags": [],
        })
    return out


def regenerate_overviews(cfg: Dict[str, Any], graph=None) -> Dict[str, Any]:
    """Regenerate every facet overview page from graph state. THIN I/O, idempotent.

    Queries the site_published Story/Usage blog nodes, groups them by facet, and writes
    ``<site_root>/facets/<facet>.html`` for each facet that has at least one journey —
    re-rendering in place (regeneration-stable). A KNOWN facet page whose facet has no
    journeys this run is REMOVED (a facet page must always reflect current graph state —
    e.g. a framework re-faceted away leaves no stale page behind); only the four known
    facet filenames are ever touched. Writes/removes files ONLY; never commits/pushes
    (the working copy stays dirty; the nightly flow / commander owns git). Returns
    {status, written: {facet: path}, removed: [paths]}; never raises for an absent
    graph — reports it.
    """
    if graph is None:
        from .publish import _carton
        graph, _sp, _q = _carton()
        if graph is None:
            logger.error("overviews: no carton connection — skipped")
            return {"status": "no_connection", "written": {}}
    rows = _query_published_blogs(graph)
    grouped = group_by_facet(rows)
    facets_dir = Path(cfg["site_root"]) / "facets"
    facets_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, str] = {}
    for facet, data in grouped.items():
        if not data["journeys"]:
            continue
        html_page = facet_overview(facet, data["journeys"], data["frameworks"])
        path = facets_dir / f"{facet}.html"
        path.write_text(html_page)
        written[facet] = str(path)
        logger.info("overviews: wrote %s (%d journeys, %d frameworks)",
                    path, len(data["journeys"]), len(data["frameworks"]))
    removed: List[str] = []
    for facet in FACETS:
        stale = facets_dir / f"{facet}.html"
        if facet not in written and stale.exists():
            stale.unlink()
            removed.append(str(stale))
            logger.info("overviews: removed stale facet page %s (no journeys)", stale)
    return {"status": "done", "written": written, "removed": removed}
