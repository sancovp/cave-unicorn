"""Pure tests for the website-update-system build:
  (A) crosslink   — chapter-nav link computation + rendering (permutations, determinism)
  (B) overviews   — facet classification, title derivation, grouping, page rendering
  (C) update_wire — the SACRED-guild refusal gate + the disabled path

All pure / no-network: (A) and (B) never touch neo4j; (C) tests only the gate (which
raises BEFORE any executor/network) and the config-disabled skip.
"""
import json
import os

import pytest

from cave_unicorn import crosslink, overviews, site, update_wire


# ═══════════════════════════════════════════════════════════════════════════
# (A) crosslink
# ═══════════════════════════════════════════════════════════════════════════

def test_kind_of():
    assert crosslink.kind_of("Site_Publish_Foo_Story_Blog") == "story"
    assert crosslink.kind_of("Site_Publish_Foo_Usage_Blog") == "usage"
    assert crosslink.kind_of("Blog_Request_Random") is None
    assert crosslink.kind_of("") is None


def test_chapter_nav_links_story_full():
    """A STORY blog with a published sibling + funnel → usage link FIRST, funnel SECOND."""
    node = {"concept": "Site_Publish_Gas_Story_Blog"}
    sibling = {"site_url": "https://x/blog/run-gas.html"}
    links = crosslink.chapter_nav_links(node, sibling, "https://x/join.html", "Join SR")
    assert len(links) == 2
    assert links[0]["url"] == "https://x/blog/run-gas.html"
    assert links[1] == {"label": "Join SR", "url": "https://x/join.html"}


def test_chapter_nav_links_story_missing_sibling():
    """No published sibling → only the funnel link (never invents the sibling)."""
    node = {"concept": "Site_Publish_Gas_Story_Blog"}
    links = crosslink.chapter_nav_links(node, {}, "https://x/join.html")
    assert [l["url"] for l in links] == ["https://x/join.html"]


def test_chapter_nav_links_story_missing_funnel():
    """No funnel URL → only the sibling link (funnel simply absent, no error)."""
    node = {"concept": "Site_Publish_Gas_Story_Blog"}
    sibling = {"site_url": "https://x/blog/run-gas.html"}
    links = crosslink.chapter_nav_links(node, sibling, None)
    assert [l["url"] for l in links] == ["https://x/blog/run-gas.html"]


def test_chapter_nav_links_story_missing_both():
    node = {"concept": "Site_Publish_Gas_Story_Blog"}
    assert crosslink.chapter_nav_links(node, None, None) == []


def test_chapter_nav_links_usage_links_funnel_only():
    """A USAGE blog links the funnel ONLY — never a sibling backlink to the story."""
    node = {"concept": "Site_Publish_Gas_Usage_Blog"}
    sibling = {"site_url": "https://x/blog/gas-story.html"}
    links = crosslink.chapter_nav_links(node, sibling, "https://x/join.html")
    assert [l["url"] for l in links] == ["https://x/join.html"]


def test_chapter_nav_links_usage_no_funnel():
    node = {"concept": "Site_Publish_Gas_Usage_Blog"}
    assert crosslink.chapter_nav_links(node, {}, None) == []


def test_chapter_nav_links_non_blog_node_empty():
    assert crosslink.chapter_nav_links({"concept": "Blog_Request_X"}, {}, "https://x/j") == []


def test_render_chapter_nav_empty():
    assert crosslink.render_chapter_nav([]) == ""


def test_render_chapter_nav_block():
    links = [{"label": "Read the usage manual", "url": "https://x/run.html"},
             {"label": "Join Sanctuary Revolution", "url": "https://x/join.html"}]
    html = crosslink.render_chapter_nav(links)
    assert "blog-cta blog-cta-build" in html
    assert 'class="blog-cta-primary"' in html   # first link is the primary button
    assert 'class="blog-cta-secondary"' in html  # rest are secondary
    assert 'href="https://x/run.html"' in html
    assert 'href="https://x/join.html"' in html
    assert "Keep going" in html


def test_render_chapter_nav_escapes():
    links = [{"label": "A & B <tag>", "url": "https://x/a?b=1&c=2"}]
    html = crosslink.render_chapter_nav(links)
    assert "A &amp; B &lt;tag&gt;" in html
    assert "b=1&amp;c=2" in html


def test_render_chapter_nav_deterministic():
    links = [{"label": "L", "url": "https://x/y.html"}]
    assert crosslink.render_chapter_nav(links) == crosslink.render_chapter_nav(links)


# ═══════════════════════════════════════════════════════════════════════════
# (B) overviews
# ═══════════════════════════════════════════════════════════════════════════

def test_facet_of_sanctum_from_part_of():
    assert overviews.facet_of(["Sanctum_Rituals", "L6_Framework"]) == "sanctum"


def test_facet_of_default_paiab():
    assert overviews.facet_of([], []) == "paiab"
    assert overviews.facet_of(["L6_Framework"]) == "paiab"


def test_facet_of_cave_and_starsystem():
    assert overviews.facet_of(["Cave_Automation"]) == "cave"
    assert overviews.facet_of(["Starsystem_Dev"]) == "starsystem"
    assert overviews.facet_of([], ["paiab"]) == "paiab"


def test_journey_title_derivation():
    assert overviews.journey_title(
        "Site_Publish_Grand_Argument_Synthesis_Gas_Story_Blog",
        "Grand_Argument_Synthesis_Gas") == "Grand Argument Synthesis Gas: The Story"
    assert overviews.journey_title(
        "Site_Publish_Grand_Argument_Synthesis_Gas_Usage_Blog",
        "Grand_Argument_Synthesis_Gas") == "Run Grand Argument Synthesis Gas Yourself"


def test_group_by_facet():
    rows = [
        {"node": "Site_Publish_Gas_Story_Blog", "site_url": "https://x/story.html",
         "published_at": "2026-07-19T04:19:37", "framework": "Gas",
         "funnel_url": "https://x/join.html", "funnel_label": "Join SR",
         "framework_part_of": ["Sanctum_Rituals"], "framework_tags": []},
        {"node": "Site_Publish_Gas_Usage_Blog", "site_url": "https://x/run.html",
         "published_at": "2026-07-20T04:19:37", "framework": "Gas",
         "funnel_url": "https://x/join.html", "funnel_label": "Join SR",
         "framework_part_of": ["Sanctum_Rituals"], "framework_tags": []},
    ]
    grouped = overviews.group_by_facet(rows)
    assert set(grouped) == {"sanctum"}
    j = grouped["sanctum"]["journeys"]
    assert len(j) == 2
    assert j[0]["url"] == "https://x/run.html"  # newest first (07-20 before 07-19)
    fws = grouped["sanctum"]["frameworks"]
    assert len(fws) == 1
    assert fws[0]["usage_url"] == "https://x/run.html"  # framework card links the deeper usage blog
    assert fws[0]["funnel_url"] == "https://x/join.html"


def test_facet_overview_renders():
    journeys = [{"title": "Gas: The Story", "url": "https://x/story.html", "date": "2026-07-19"}]
    frameworks = [{"name": "Gas", "title": "Gas", "usage_url": "https://x/run.html",
                   "funnel_url": "https://x/join.html", "funnel_label": "Join SR"}]
    html = overviews.facet_overview("sanctum", journeys, frameworks)
    assert "SANCTUM" in html
    assert "Journeys" in html and "Frameworks" in html
    assert 'href="https://x/story.html"' in html   # journey card links the post (absolute url)
    assert 'href="https://x/run.html"' in html      # framework card links the usage blog
    assert 'href="https://x/join.html"' in html      # ...and the funnel
    assert "blog-card" in html
    assert '../blog/blog-style.css' in html          # reuses the site's blog chrome


def test_facet_overview_empty_journeys():
    html = overviews.facet_overview("cave", [], [])
    assert "No posts yet." in html


def test_group_by_facet_explicit_facet_overrides_heuristic():
    """An explicit framework ``facet`` property beats the part_of keyword heuristic
    (part_of edges can be composition-session residue — the GAS/Sanctum_Rituals case);
    a value that is not a real facet name is IGNORED and the heuristic applies."""
    row = {"node": "Site_Publish_Gas_Story_Blog", "site_url": "https://x/story.html",
           "published_at": "2026-07-19", "framework": "Gas",
           "funnel_url": None, "funnel_label": None,
           "framework_part_of": ["Sanctum_Rituals"], "framework_tags": []}
    assert set(overviews.group_by_facet([{**row, "framework_facet": "paiab"}])) == {"paiab"}
    assert set(overviews.group_by_facet([{**row, "framework_facet": "PAIAB"}])) == {"paiab"}
    assert set(overviews.group_by_facet([{**row, "framework_facet": "bogus"}])) == {"sanctum"}
    assert set(overviews.group_by_facet([row])) == {"sanctum"}


class _StubGraph:
    """execute_query stub returning canned published-blog rows (no neo4j)."""
    def __init__(self, rows):
        self._rows = rows

    def execute_query(self, _cypher, _params):
        return self._rows


def test_regenerate_overviews_writes_and_removes_stale(tmp_path):
    """regenerate_overviews writes facets/<facet>.html for facets with journeys and
    REMOVES a known facet page whose facet lost all journeys (re-faceting leaves no
    stale page); never touches unknown filenames."""
    cfg = {"site_root": str(tmp_path)}
    row = {"node": "Site_Publish_Gas_Usage_Blog", "site_url": "https://x/run.html",
           "published_at": "2026-07-20", "framework": "Gas",
           "funnel_url": None, "funnel_label": None, "framework_facet": "paiab",
           "framework_part_of": ["Sanctum_Rituals"]}
    facets_dir = tmp_path / "facets"
    facets_dir.mkdir()
    (facets_dir / "sanctum.html").write_text("stale")
    (facets_dir / "unrelated.html").write_text("keep me")

    out = overviews.regenerate_overviews(cfg, graph=_StubGraph([row]))
    assert out["status"] == "done"
    assert set(out["written"]) == {"paiab"}
    assert (facets_dir / "paiab.html").exists()
    assert not (facets_dir / "sanctum.html").exists()          # stale facet retired
    assert (facets_dir / "unrelated.html").read_text() == "keep me"
    assert out["removed"] == [str(facets_dir / "sanctum.html")]
    # idempotent second run: same write, nothing further removed
    out2 = overviews.regenerate_overviews(cfg, graph=_StubGraph([row]))
    assert out2["written"] == out["written"] and out2["removed"] == []


# ═══════════════════════════════════════════════════════════════════════════
# (B2) site — re-publish tag preservation
# ═══════════════════════════════════════════════════════════════════════════

_INDEX_WITH_CARD = (
    '<div style="display:grid;gap:1rem;" id="posts">\n'
    '      <a href="gas.html" class="blog-card" data-tags="paiab admissibility-eng" '
    'data-search="x"><h3>T</h3><p>H</p><span class="read-link">Read &rarr;</span></a>\n'
    '</div>'
)


def test_existing_card_tags_reads_curated_tags():
    assert site.existing_card_tags(_INDEX_WITH_CARD, "gas.html") == \
        ["paiab", "admissibility-eng"]


def test_existing_card_tags_none_when_no_card():
    assert site.existing_card_tags(_INDEX_WITH_CARD, "other.html") is None
    assert site.existing_card_tags("", "gas.html") is None


def test_funnel_slug_of():
    from cave_unicorn.publish import funnel_slug_of
    assert funnel_slug_of("Site_Publish_Grand_Argument_Synthesis_Gas_Funnel") == \
        "grand-argument-synthesis-gas"
    assert funnel_slug_of("Site_Publish_X_Funnel") == "x"


def test_publish_funnel_file_stages_root_page(tmp_path):
    """The funnel lane copies the rendered page VERBATIM to
    <site_root>/funnel-<slug>.html — no skeleton wrap, no index card; the report
    carries the update-wire fields (title + live_url)."""
    page = "<!DOCTYPE html>\n<html><body>certified funnel</body></html>\n"
    src = tmp_path / "funnel.html"
    src.write_text(page)
    cfg = {"site_root": str(tmp_path), "push": False,
           "site_base_url": "https://x.github.io/site"}
    report = site.publish_funnel_file(str(src), cfg, slug="gas", commit=False)
    out = tmp_path / "funnel-gas.html"
    assert out.read_text() == page                       # verbatim, never wrapped
    assert report["status"] == "staged"
    assert report["title"] == "Gas funnel"
    assert report["index_card"] == "none"
    assert report["live_url"] == "https://x.github.io/site/funnel-gas.html"
    # regeneration-stable: re-publish overwrites the same file
    report2 = site.publish_funnel_file(str(src), cfg, slug="gas", commit=False)
    assert report2["live_url"] == report["live_url"]


def test_insert_card_replacement_with_preserved_tags_keeps_curation():
    """The publish_file re-publish path resolves tags via existing_card_tags before
    insert_card — proving the curated tags survive a default-tags re-publish (the
    2026-07-20 regression: GAS cards degraded to data-tags=\"unicorn\")."""
    preserved = site.existing_card_tags(_INDEX_WITH_CARD, "gas.html")
    new_index, status = site.insert_card(
        _INDEX_WITH_CARD, "gas.html", "T2", "H2", preserved, "search terms")
    assert status == "updated"
    assert 'data-tags="paiab admissibility-eng"' in new_index
    assert "unicorn" not in new_index


# ═══════════════════════════════════════════════════════════════════════════
# (C) update_wire — the SACRED-guild refusal gate + disabled path
# ═══════════════════════════════════════════════════════════════════════════

def test_assert_guild_allowed_refuses_sacred_twi():
    with pytest.raises(RuntimeError, match="SACRED TWI"):
        update_wire.assert_guild_allowed("1034897954542207116", allow_live=False)


def test_assert_guild_allowed_refuses_sacred_gnosys():
    with pytest.raises(RuntimeError, match="SACRED GNOSYS"):
        update_wire.assert_guild_allowed("1439317050999705933", allow_live=False)


def test_assert_guild_allowed_sacred_with_allow_live_passes():
    # allow_live=True is the ONLY override; returns None (no raise).
    assert update_wire.assert_guild_allowed("1439317050999705933", allow_live=True) is None


def test_assert_guild_allowed_non_sacred_passes():
    assert update_wire.assert_guild_allowed("1514855634472796300", allow_live=False) is None


def test_notify_publish_disabled_when_unconfigured():
    """Absent notify_actor / updates_guild_config ⟹ skipped, never a crash."""
    out = update_wire.notify_publish({"title": "T", "live_url": "https://x"}, {})
    assert out["status"] == "skipped"
    out2 = update_wire.notify_publish(
        {"title": "T", "live_url": "https://x"},
        {"notify_actor": "GNOSYS", "updates_guild_config": None})
    assert out2["status"] == "skipped"


def test_notify_publish_gate_raises_on_sacred_guild(tmp_path):
    """A configured guild whose id is SACRED (no allow_live) ⟹ the wire RAISES (refuses)
    before any network call."""
    gc = tmp_path / "sacred_guild.json"
    gc.write_text(json.dumps({"token": "x", "guild_id": "1439317050999705933",
                              "channels": {"updates": "1"}}))
    with pytest.raises(RuntimeError, match="SACRED GNOSYS"):
        update_wire.notify_publish(
            {"title": "T", "live_url": "https://x"},
            {"notify_actor": "GNOSYS", "updates_guild_config": str(gc)})


def test_notify_publish_missing_guild_config_raises(tmp_path):
    """A configured-but-missing guild config file raises loudly (no silent skip)."""
    with pytest.raises(FileNotFoundError):
        update_wire.notify_publish(
            {"title": "T", "live_url": "https://x"},
            {"notify_actor": "GNOSYS",
             "updates_guild_config": str(tmp_path / "nope.json")})
