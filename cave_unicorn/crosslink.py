"""Chapter cross-link injection — the publish-time nav block (deliverable A).

Every manual publishing event renders TWO blog posts: a STORY blog (blog 1) and a
USAGE blog (blog 2). Isaac's chapter topology (verbatim): "The first blog post links
to the second one and the funnel, the second one links to the funnel." This module
computes those links from GRAPH METADATA and renders an HTML nav block that the
PUBLISHER injects into the page SKELETON at render time — the certified markdown
bodies are NEVER touched (that is the long-standing "no cross-links because adding
them edits the certified body" gap, resolved here at the publisher).

The KIND of a page is read off its Site_Publish node name:
``Site_Publish_<Framework>_Story_Blog`` / ``Site_Publish_<Framework>_Usage_Blog``.
A page with neither suffix (e.g. a plain Blog_Request-lane post) has no chapter kind
and gets NO block — missing pieces mean fewer links, never invented, never an error.

PURE CORE (no I/O): ``chapter_nav_links`` computes the link list; ``render_chapter_nav``
renders it to an HTML block in the site's existing blog-cta css vocabulary (blog-style.css:
.blog-cta / .blog-cta-build / .blog-cta-actions / .blog-cta-primary / .blog-cta-secondary —
no new CSS). The graph query that assembles the args lives in publish.py (which has the
carton connection); this module never touches neo4j.
"""

from __future__ import annotations

import html as _html
from typing import Any, Dict, List, Optional


def kind_of(concept_name: str) -> Optional[str]:
    """The chapter KIND of a Site_Publish node, read off its name suffix.

    Returns ``"story"`` for ``*_Story_Blog``, ``"usage"`` for ``*_Usage_Blog``,
    and ``None`` for any other name (a page with no chapter identity → no block).
    """
    if concept_name.endswith("_Story_Blog"):
        return "story"
    if concept_name.endswith("_Usage_Blog"):
        return "usage"
    return None


def chapter_nav_links(
    node_props: Dict[str, Any],
    sibling_props: Optional[Dict[str, Any]],
    funnel_url: Optional[str],
    funnel_label: str = "Join Sanctuary Revolution",
) -> List[Dict[str, str]]:
    """Compute the chapter-nav links for one blog page from graph metadata. PURE.

    ``node_props`` — the Site_Publish node's properties, and MUST carry a
    ``"concept"`` key = the node name (so the chapter kind is derivable).
    ``sibling_props`` — the sibling Site_Publish node's properties (its
    ``"site_url"`` is the sibling-chapter link), or None/{} when there is no
    published sibling.
    ``funnel_url`` — the framework's funnel page URL (the graph's
    ``funnel_cta_url``); None/"" ⟹ the funnel link is simply absent.
    ``funnel_label`` — the CTA text for the funnel link.

    Topology (Isaac, verbatim): a STORY blog links its USAGE sibling (when that
    sibling's site_url exists) + the funnel (when funnel_url exists); a USAGE blog
    links the funnel only. Any missing piece drops that one link — nothing is
    invented and no error is raised. A node with no chapter kind returns [].
    """
    kind = kind_of(str(node_props.get("concept", "")))
    links: List[Dict[str, str]] = []
    if kind is None:
        return links
    if kind == "story":
        sibling_url = (sibling_props or {}).get("site_url")
        if sibling_url:
            links.append({"label": "Read the usage manual", "url": str(sibling_url)})
    if funnel_url:
        links.append({"label": funnel_label, "url": str(funnel_url)})
    return links


def render_chapter_nav(links: List[Dict[str, str]]) -> str:
    """Render chapter-nav links to an HTML block, or "" when there are none. PURE.

    Uses ONLY existing blog-style.css classes (a .blog-cta.blog-cta-build card with
    .blog-cta-actions; the first link is the .blog-cta-primary button, the rest are
    .blog-cta-secondary). The violet 'build' accent distinguishes it from the blue
    'learn' CTA already in the post skeleton. Labels + URLs are HTML-escaped.
    An empty link list renders to "" so a page with no chapter metadata gets no block.
    """
    if not links:
        return ""
    action_lines: List[str] = []
    for i, link in enumerate(links):
        cls = "blog-cta-primary" if i == 0 else "blog-cta-secondary"
        url = _html.escape(str(link.get("url", "")), quote=True)
        label = _html.escape(str(link.get("label", "")))
        action_lines.append(
            f'      <a href="{url}" class="{cls}">{label} &rarr;</a>'
        )
    actions = "\n".join(action_lines)
    return (
        '\n  <!-- Chapter navigation (injected at publish time; the md body is untouched) -->\n'
        '  <div class="blog-cta blog-cta-build">\n'
        '    <p class="blog-cta-label">Keep going</p>\n'
        '    <div class="blog-cta-actions">\n'
        f'{actions}\n'
        '    </div>\n'
        '  </div>\n'
    )
