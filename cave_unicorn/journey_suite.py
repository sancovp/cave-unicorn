"""journey_suite — deterministic multi-platform renders from ONE filled JourneyCore.

The 'fill once, derive everywhere' doctrine (cave_discord.content.core docstring)
made real: the AGENT's only job is to fill TWO JSONs (journey_core.json +
journey_blog.json, per the live field contract this module prints); everything
else renders DETERMINISTICALLY here:

  - blog-aida.md   = JourneyBlog(**blog_json).render()   (the AIDA-within-AIDA blog)
  - pack.md        = TwitterPostSet/LinkedInPost/DiscordJourneyPost .from_core(core)
                     .render() + the agent's IMAGE PROMPTS passthrough
  - journey_core.json = the validated core (persisted so downstream organs reuse it)

Model homes: ALL THREE modules (core.py, renderers.py, templates.py) load BY
PATH from integration/cave-discord-fork — the fork is the LIVE source the blog
organ actually uses. The cave_discord.content "absorbed" copies are STALE
(verified 2026-07-10: content.core still has the old Literal domain enum and
lacks the framework-blog fields; templates.py was never absorbed at all) —
the absorption needs a refresh in cave-discord, flagged, not silently papered
over here.

`python3 -m cave_unicorn.journey_suite --contract` prints the LIVE field
contract (name + description per model) — the agent prompt tells the agent to
read it, so the instructions can never drift from the models.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

FORK_DIR = os.environ.get(
    "JOURNEYCORE_IMPORT_PATH",  # same env the blog organ honors
    "/home/GOD/gnosys-plugin-v2/integration/cave-discord-fork",
)


def _load_fork_modules():
    """Load core/renderers/templates from the fork dir (the LIVE models).

    renderers.py does a flat `from core import JourneyCore`, so the fork dir
    goes on sys.path — the fork's own established loading idiom (its
    publish_bridge.py documents adding the dir defensively for exactly this
    reason). The collision hazard of the generic names 'core'/'templates' is
    handled by the origin CHECK below: a wrong resolution fails loud, never
    silently renders with someone else's model."""
    if FORK_DIR not in sys.path:
        sys.path.insert(0, FORK_DIR)
    mods = {}
    for name in ("core", "renderers", "templates", "framework_render"):
        mod = importlib.import_module(name)
        origin = getattr(mod, "__file__", "") or ""
        if not origin.startswith(FORK_DIR):
            raise ImportError(
                f"module {name!r} resolved to {origin!r}, not the fork at "
                f"{FORK_DIR} — refusing to render with the wrong model")
        mods[name] = mod
    return mods["core"], mods["renderers"], mods["templates"], mods["framework_render"]


def field_contract() -> Dict[str, Dict[str, str]]:
    """The LIVE fill contract: {model: {field: 'REQUIRED|optional: description'}}."""
    core_mod, _renderers, templates, _framework_render = _load_fork_modules()
    out: Dict[str, Dict[str, str]] = {}
    for name, model in (("journey_core", core_mod.JourneyCore),
                        ("journey_blog", templates.JourneyBlog)):
        out[name] = {
            fname: ("REQUIRED: " if f.is_required() else "optional: ")
                   + (f.description or "")
            for fname, f in model.model_fields.items()
        }
    return out


def _render_marketing_blog(blog, core, funnel_url: str | None = None) -> str:
    """Hero's-journey MARKETING render of a JourneyBlog (Isaac 2026-07-11,
    the run-3 user-gate ruling): the template's mechanic labels (The Hook /
    Let Me Show You / Take Action...) are SLOT NAMES — they are never
    published as headings; structure stays invisible and each section leads
    with its bolded attention line (sales-letter rhythm). The piece CLOSES
    with the CTA cycle as flowing copy ending in ONE funnel link — "Not link
    to github, not link to xyz. Link to *funnel about that thing*"; github
    belongs INSIDE the funnel as the conversion offer. funnel_url falls back
    to the deep-dive then the plugin (INTERIM until funnel pages exist —
    journaled 2026-07-11; the fallback is the closest funnel-shaped object,
    not the end state)."""
    def cycle(attention: str, interest: str, desire: str, action: str,
              bold_lead: bool = True) -> str:
        lead = f"**{attention}**" if bold_lead else attention
        return "\n\n".join([lead, interest, desire, action])

    parts = [f"# {blog.journey_name}"]
    parts.append(cycle(blog.hook_attention, blog.hook_interest,
                       blog.hook_desire, blog.hook_action))
    parts.append(cycle(blog.topic_attention, blog.topic_interest,
                       blog.topic_desire, blog.topic_action))
    parts.append(cycle(blog.personal_attention, blog.personal_interest,
                       blog.personal_desire, blog.personal_action))
    if blog.ad_content:
        parts.append(blog.ad_content)
    parts.append(cycle(blog.main_attention, blog.main_interest,
                       blog.main_desire, blog.main_action))
    parts.append(cycle(blog.demo_attention, blog.demo_interest,
                       blog.demo_desire, blog.demo_action))
    parts.append(cycle(blog.discuss_attention, blog.discuss_interest,
                       blog.discuss_desire, blog.discuss_action))
    if blog.announce_content:
        parts.append(blog.announce_content)

    closing = [f"**{blog.cta_attention}**", blog.cta_interest,
               blog.cta_desire, blog.cta_action]
    funnel = funnel_url or core.deep_dive_url or core.plugin_url
    if funnel:
        closing.append(f"**Start here: {funnel}**")
    parts.append("\n\n".join(closing))
    return "\n\n".join(parts) + "\n"


# THE FIXPOINT POST (Isaac 2026-07-12, verbatim spec): ONE invariant blog post
# format for all blog posts forever — a fixpoint. OVERVIEW + JOURNEY +
# FRAMEWORK. The repeating SKELETON is the brand — but only the parts a
# stranger understands on sight. Isaac 2026-07-12 on the old spine line +
# arrow transition markers: "weird as fuck ... your marketing register is
# continually assuming the user knows something they dont. You have to design
# the experience of reading the blog so that it is repetitive in a way that
# explains how the blog writer works without ever explaining it, except in
# this post [the blog-writer post]." So: plain-English stage HEADINGS repeat
# post after post (the implicit teaching); the ladder-map spine + "— crossing →"
# notation are NOT rendered; the format is explained explicitly ONLY in the
# blog-writer post's own content.
_FIXPOINT_LADDER = [
    # (visible stage heading, core field)
    ("STATUS QUO", "status_quo"),
    ("THE DEBATE", "debate"),
    ("THE TRIALS", "trials"),
    ("THE NEW VIEW", "new_view"),
    ("THE RIGHT WAY", "right_way"),
    ("THE BOON", "the_boon"),
    ("THE WORLD OF MASTERY", "world_of_mastery"),
]
_FIXPOINT_REQUIRED = (
    ["hook", "overview_pain", "overview_solution", "overview_dream",
     "framework_statement", "build_time"]
    + [f for _h, f in _FIXPOINT_LADDER]
)


def _render_receipts_section(core) -> str:
    """THE RECEIPTS — the GAS proof slots rendered visible (Isaac 2026-07-13,
    phase-A: "GAS proofs / even just copying the proof slots will help").

    Renders ONLY when the proof pair is present (grand_argument_claim AND
    premises) — absent = section absent, no fallbacks. A PARTIAL fill (one of
    the pair, or theme floating alone, or a premise entry without its
    '|receipt') raises loudly: a proof section is complete or it does not
    render. Each premise entry is 'premise|receipt' (the skill_urls 'a|b'
    convention); the receipt is the scene that instantiates the premise, per
    the GAS cert ladder (foundation.pl: grand_argument premises are
    instantiated by scenes; theme is the claim proved by the grand argument).
    """
    claim = getattr(core, "grand_argument_claim", None)
    premises = getattr(core, "premises", None)
    theme = getattr(core, "theme", None)
    if not (claim or premises or theme):
        return ""
    if not (claim and premises):
        missing = [n for n, v in (("grand_argument_claim", claim),
                                  ("premises", premises)) if not v]
        raise ValueError(
            "GAS proof slots partially filled — the receipts section needs "
            f"grand_argument_claim AND premises; missing: {missing}")

    lines = ["## THE RECEIPTS", f"**The claim:** {claim}"]
    for entry in premises:
        if "|" not in entry:
            raise ValueError(
                "malformed premise entry (expected 'premise|receipt'): "
                f"{entry!r}")
        premise, receipt = entry.split("|", 1)
        lines.append(f"- {premise.strip()} — *receipt:* {receipt.strip()}")
    if theme:
        lines.append(f"**The lesson:** {theme}")
    return "\n\n".join(lines)


def render_fixpoint_post(core, funnel_url: str | None = None) -> str:
    """THE ONE INVARIANT POST FORMAT — OVERVIEW + JOURNEY + FRAMEWORK.

    The seven stage headings render VISIBLE and identical in every post —
    the repetition itself teaches the format (never notation a stranger
    can't parse; the spine line + arrow transition markers were removed per
    Isaac 2026-07-12). All links are real markdown anchors (bare URLs never
    autolink on the site — live-found). Raises loudly on any missing
    fixpoint field: no fallbacks, a fixpoint post is complete or it does
    not render.
    """
    missing = [f for f in _FIXPOINT_REQUIRED if not getattr(core, f, None)]
    if missing:
        raise ValueError(f"fixpoint post is incomplete — missing fields: {missing}")

    parts = [f"# {core.journey_name}", f"**{core.hook}**"]

    # ── OVERVIEW: TLDR — THIS PAIN -> DREAM -> MY SOLUTION. Dream before
    # solution ALWAYS (Isaac 2026-07-12, verbatim: "nobody cares how the
    # plane works they care about hawaii. they definitely dont give a single
    # fuck about the peanuts on the flight or the seats or the pilots") —
    # the solution leg is the ticket to the dream, never mechanism detail. ──
    parts.append("\n\n".join([
        "## OVERVIEW",
        f"**The pain:** {core.overview_pain}",
        f"**The dream:** {core.overview_dream}",
        f"**My solution:** {core.overview_solution}",
    ]))

    # ── THE JOURNEY: the seven plain-English stage headings, nothing cryptic ──
    journey = ["## THE JOURNEY"]
    for heading, field in _FIXPOINT_LADDER:
        journey.append(f"### {heading}")
        journey.append(getattr(core, field))
    parts.append("\n\n".join(journey))

    receipts = _render_receipts_section(core)
    if receipts:
        parts.append(receipts)

    # ── THE FRAMEWORK: WE SOLVED THIS + the facts, every link a real anchor ──
    fw = ["## THE FRAMEWORK", f"**We solved this.** {core.framework_statement}"]
    repo = core.github_url or core.plugin_url
    if repo:
        fw.append(f"**See it on GitHub:** [{repo.split('//', 1)[-1]}]({repo})")
    fw.append(f"**Build it yourself:** {core.build_time}")
    if core.deep_dive_url:
        fw.append("**How this fits the whole system:** "
                  f"[the global view]({core.deep_dive_url})")
    funnel = funnel_url or core.deep_dive_url or core.plugin_url
    if funnel:
        fw.append(f"**[Start here]({funnel})**")
    parts.append("\n\n".join(fw))

    return "\n\n".join(parts) + "\n"


# The Isaac-APPROVED story-beat headings (the live skilltree chapter opener he
# passed): content-shaped STORY BEATS, never renderer-mechanic slot names. An
# agent may override per blog with headings AUTHORED from the content.
_DEFAULT_BEAT_HEADINGS = {
    "status_quo": "Where I was",
    "obstacle": "The wall",
    "overcome": "The turn",
    "the_boon": "The boon",
}


def render_chapter_blog(core, beat_headings: Dict[str, str] | None = None,
                        cta_copy: str | None = None,
                        funnel_url: str | None = None) -> str:
    """NARRATIVE CHAPTER render of a JourneyCore (Blog 1 of a framework chapter).

    Replaces the fork's framework_blog_from_core as the chapter-lane renderer
    (Isaac 2026-07-11, the composed-run gate ruling): that renderer's fixed slot
    names (The Story / The Key Insight / Demo / Why This Matters / Take Action)
    and bare emoji link lines are the SAME mechanic-scaffolding class rejected
    on the AIDA render — structure stays invisible. Here the section headings
    are STORY BEATS (agent-authored via beat_headings, defaulting to the
    approved skilltree chapter shape), and the piece CLOSES with flowing CTA
    copy (cta_copy — authored by the fill agent, carrying the framework's four
    facts and the deep-dive link woven as prose) ending in ONE Start-here
    funnel link. funnel_url falls back to deep_dive_url then plugin_url
    (INTERIM until funnel pages exist — same rule as the marketing render).
    The fork file stays frozen; the chapter render law lives here.
    """
    h = dict(_DEFAULT_BEAT_HEADINGS)
    if beat_headings:
        h.update(beat_headings)

    parts = [f"# {core.journey_name}"]
    if core.hook:
        parts.append(f"**{core.hook}**")

    parts.append("\n\n".join([f"## {h['status_quo']}", core.status_quo]))
    parts.append("\n\n".join([f"## {h['obstacle']}", core.obstacle]))
    parts.append("\n\n".join([f"## {h['overcome']}", core.overcome,
                              f"**{core.accomplishment}**"]))

    boon = [f"## {h['the_boon']}", core.the_boon]
    if core.why_this_matters:
        boon.append(core.why_this_matters)
    parts.append("\n\n".join(boon))

    # Closing = flowing copy, NO heading, ONE funnel link (never emoji link
    # lines, never a links section — github lives INSIDE the funnel).
    closing: list = []
    if core.universal_application:
        closing.append(core.universal_application)
    if cta_copy:
        closing.append(cta_copy)
    funnel = funnel_url or core.deep_dive_url or core.plugin_url
    if funnel:
        closing.append(f"**Start here: {funnel}**")
    if closing:
        parts.append("\n\n".join(closing))

    return "\n\n".join(parts) + "\n"


def _build_pack_md(core, renderers, image_prompts_path: str | None) -> str:
    """The socials pack body: twitter/linkedin/discord from_core renders +
    the agent's image prompts passthrough + the source footer."""
    sections = [
        f"# Socials pack — {core.journey_name}",
        "\n## TWITTER/X\n\n" + renderers.TwitterPostSet.from_core(core).render(),
        "\n## LINKEDIN\n\n" + renderers.LinkedInPost.from_core(core).render(),
        "\n## DISCORD\n\n" + renderers.DiscordJourneyPost.from_core(core).render(),
    ]
    if image_prompts_path and Path(image_prompts_path).exists():
        sections.append("\n## IMAGE PROMPTS\n\n"
                        + Path(image_prompts_path).read_text().strip())
    sections.append("\n## SOURCE\n\n- core: journey_core.json (validated)\n"
                    f"- blog: {core.blog_url or '(unset)'}")
    return "\n".join(sections) + "\n"


def render_suite(core_json_path: str, blog_json_path: str, out_dir: str,
                 image_prompts_path: str | None = None,
                 funnel_url: str | None = None) -> Dict[str, Any]:
    """Validate the two fills and render every platform artifact. Raises on an
    invalid fill (the agent must fix its JSON — no silent partial renders)."""
    core_mod, renderers, templates, _framework_render = _load_fork_modules()

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    core = core_mod.JourneyCore(**json.loads(Path(core_json_path).read_text()))
    blog = templates.JourneyBlog(**json.loads(Path(blog_json_path).read_text()))

    (out / "blog-aida.md").write_text(_render_marketing_blog(blog, core, funnel_url))

    (out / "pack.md").write_text(_build_pack_md(core, renderers, image_prompts_path))

    (out / "journey_core.json").write_text(core.model_dump_json(indent=2) + "\n")

    logger.info("journey_suite: rendered blog-aida.md + pack.md in %s", out)
    return {"status": "rendered",
            "blog_aida": str(out / "blog-aida.md"),
            "pack": str(out / "pack.md"),
            "core": str(out / "journey_core.json")}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m cave_unicorn.journey_suite")
    parser.add_argument("--contract", action="store_true",
                        help="print the live fill contract and exit")
    parser.add_argument("--core")
    parser.add_argument("--blog")
    parser.add_argument("--out")
    parser.add_argument("--image-prompts", dest="image_prompts")
    parser.add_argument("--funnel-url", dest="funnel_url",
                        help="the ONE closing funnel link (falls back to the "
                             "core's deep_dive_url then plugin_url)")
    args = parser.parse_args()
    if args.contract:
        print(json.dumps(field_contract(), indent=2))
    else:
        if not (args.core and args.blog and args.out):
            parser.error("--core, --blog and --out are required to render")
        print(json.dumps(render_suite(args.core, args.blog, args.out,
                                      args.image_prompts, args.funnel_url),
                         indent=2))
