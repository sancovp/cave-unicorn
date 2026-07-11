"""The blog -> website connector: render a produced blog markdown into the live
site's blog (aisaac GitHub Pages shape) and wire it into the blog index.

The site shape this targets (verified against /home/GOD/aisaac/blog 2026-07-10):
  - each post = a standalone ``{slug}.html`` using the site skeleton
    (site-header nav, ``<article>`` with post-tag month / h1 / post-subtitle,
    body, blog-CTA block, site-footer, sticky-cta.js);
  - ``index.html`` holds a card grid ``<div ... id="posts">`` of
    ``<a href="{slug}.html" class="blog-card" data-tags data-search>`` cards and a
    static ``result-count`` ("N posts") that client JS recomputes on filter.

Blog source contract (what the blog organ / skill2framework emit): markdown whose
first ``# `` line is the title and whose first ``*...*`` paragraph after it is the
hook/subtitle; the rest is the body.

Git: publish_file stages exactly the post + index, commits, and (when push=True)
pulls --rebase --autostash then pushes. Any git failure raises — no silent
fallbacks; the automation wrapper (publish.fire_site_publish) catches and reports.
"""

from __future__ import annotations

import html as _html
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import markdown as _markdown

logger = logging.getLogger(__name__)

MD_EXTENSIONS = ["fenced_code", "tables"]

POST_TEMPLATE = """<link rel="stylesheet" href="blog-style.css">
<div id="isaac-site">
  <div class="site-header">
    <a href="../index.html" class="logo">Isaac — TWI</a>
    <div class="nav-links">
      <a href="./" class="nav-link">Blog</a>
      <a href="../frameworks.html" class="nav-link">Frameworks</a>
      <a href="../apply.html" class="nav-cta">Book a Call</a>
    </div>
  </div>

  <article>
    <div class="post-tag">{month}</div>
    <h1>{title}</h1>
    <p class="post-subtitle">{hook}</p>

{body}
  </article>

  <!-- Blog CTA -->
  <div class="blog-cta blog-cta-learn">
    <p class="blog-cta-label">Want to go deeper?</p>
    <p class="blog-cta-desc">Frameworks, architecture, the 7-stack methodology. Free content that shows you how compound AI systems actually work.</p>
    <div class="blog-cta-actions">
      <a href="../learn.html" class="blog-cta-primary">Keep Learning</a>
      <a href="../apply.html" class="blog-cta-secondary">Or book a call &rarr;</a>
    </div>
  </div>

  <div class="site-footer">
    <span>&copy; 2026 Isaac &mdash; TWI Consulting</span>
    <span><a href="../index.html" style="color:var(--amber);text-decoration:none;">&larr; Home</a></span>
  </div>
</div>
<script src="../sticky-cta.js"></script>
<script src="../newsletter.js"></script>
"""

CARD_TEMPLATE = ('      <a href="{href}" class="blog-card" data-tags="{tags}" '
                 'data-search="{search}"><h3>{title}</h3><p>{hook}</p>'
                 '<span class="read-link">Read &rarr;</span></a>')

_POSTS_OPEN_RE = re.compile(r'(<div [^>]*id="posts"[^>]*>\n)')
_COUNT_RE = re.compile(r'(<div class="result-count" id="count">)(\d+) posts(</div>)')


def split_front(md_text: str) -> Tuple[str, str, str]:
    """Split blog markdown into (title, hook, body_md).

    title = the first ``# `` heading line; hook = the first ``*...*``-wrapped
    paragraph after it (optional — empty string if absent). Both are removed
    from the returned body. Raises ValueError if no title heading exists.
    """
    lines = md_text.splitlines()
    title = ""
    title_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            title_idx = i
            break
    if title_idx < 0:
        raise ValueError("blog markdown has no '# ' title heading")

    hook = ""
    hook_idx = -1
    for i in range(title_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        m = re.fullmatch(r"\*{1,2}(.+?)\*{1,2}", stripped)
        if m:
            hook = m.group(1).strip()
            hook_idx = i
        break  # only the FIRST non-empty block may be the hook (single line, * or ** wrapped)

    body_lines = [
        line for i, line in enumerate(lines)
        if i != title_idx and i != hook_idx
    ]
    return title, hook, "\n".join(body_lines).strip() + "\n"


def slugify(title: str) -> str:
    """Lowercase, alphanumerics + hyphens only (the site's filename shape)."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        raise ValueError(f"title {title!r} produced an empty slug")
    return slug


def render_post(md_text: str, month: Optional[str] = None,
                title: Optional[str] = None,
                hook: Optional[str] = None) -> Tuple[str, str, str]:
    """Render blog markdown to a full post HTML page. Returns (title, hook, html)."""
    md_title, md_hook, body_md = split_front(md_text)
    title = title or md_title
    hook = hook or md_hook
    month = month or datetime.now().strftime("%B %Y")
    body_html = _markdown.markdown(body_md, extensions=MD_EXTENSIONS)
    # Indent the body to sit inside <article> like the hand-authored posts.
    body_html = "\n".join(
        ("    " + line) if line.strip() else line
        for line in body_html.splitlines()
    )
    page = POST_TEMPLATE.format(
        month=_html.escape(month),
        title=_html.escape(title),
        hook=_html.escape(hook),
        body=body_html,
    )
    return title, hook, page


def build_search_terms(title: str, hook: str, extra: Optional[str] = None) -> str:
    """The card's data-search attr: lowercase de-duplicated words from title+hook."""
    words: List[str] = []
    for source in (title, hook, extra or ""):
        for w in re.findall(r"[a-zA-Z0-9']+", source.lower()):
            if w not in words:
                words.append(w)
    return " ".join(words)


def insert_card(index_text: str, href: str, title: str, hook: str,
                tags: List[str], search: str) -> Tuple[str, str]:
    """Insert a blog card at the TOP of the index card grid and bump the count.

    Re-publish semantics: if a card for ``href`` already exists it is REPLACED
    in place (status "updated" — count untouched) so title/hook/tag edits
    propagate; an identical card returns unchanged ("already_indexed").
    Raises ValueError if the index does not carry the posts-grid marker.
    """
    card = CARD_TEMPLATE.format(
        href=_html.escape(href, quote=True),
        tags=_html.escape(" ".join(tags), quote=True),
        search=_html.escape(search, quote=True),
        title=_html.escape(title),
        hook=_html.escape(hook),
    )

    if f'href="{href}"' in index_text:
        if card in index_text:
            return index_text, "already_indexed"
        existing_card_re = re.compile(
            r'[ \t]*<a href="' + re.escape(href) + r'" class="blog-card".*?</a>',
            re.DOTALL)
        new_text, n = existing_card_re.subn(card, index_text, count=1)
        if n != 1:
            raise ValueError(f"index card for {href} exists but could not be rewritten")
        return new_text, "updated"

    new_text, n = _POSTS_OPEN_RE.subn(r"\1\n" + card + "\n", index_text, count=1)
    if n != 1:
        raise ValueError('index.html has no <div ... id="posts"> grid marker')

    def _bump(m: "re.Match[str]") -> str:
        return f"{m.group(1)}{int(m.group(2)) + 1} posts{m.group(3)}"

    new_text, n = _COUNT_RE.subn(_bump, new_text, count=1)
    if n != 1:
        logger.warning("index.html result-count not found — count not bumped")
    return new_text, "inserted"


def _git(site_root: str, *args: str) -> str:
    """Run a git command in the site checkout; raise loudly on failure."""
    proc = subprocess.run(["git", "-C", site_root, *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {site_root} (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def publish_file(md_path: str, cfg: Dict[str, Any],
                 slug: Optional[str] = None,
                 tags: Optional[List[str]] = None,
                 month: Optional[str] = None,
                 push: Optional[bool] = None,
                 commit: bool = True,
                 title: Optional[str] = None,
                 hook: Optional[str] = None,
                 link_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Publish one blog markdown file onto the live site.

    render -> write {blog_dir}/{slug}.html -> insert index card -> git add/commit
    -> (push=True) pull --rebase --autostash + push. Returns a status dict with
    the artifact paths + live URL. Raises on render/index/git failure (the
    automation wrapper catches).

    ``title``/``hook`` override what split_front extracts (a source with no
    ``*...*`` hook line gets its subtitle this way). ``link_map`` is a plain
    ordered string replacement applied to the markdown before render (ALL
    occurrences, link targets and bare text alike) — e.g. {"./blog1.md":
    "skilltree-the-story.html"} points a chapter-bundle sibling reference at
    the published post; put longer/more-specific replacements first.
    """
    md_file = Path(md_path)
    md_text = md_file.read_text()
    for old, new in (link_map or {}).items():
        md_text = md_text.replace(old, new)
    title, hook, page_html = render_post(md_text, month=month,
                                         title=title, hook=hook)
    slug = slug or slugify(title)
    tags = tags if tags is not None else list(cfg["default_tags"])
    push = cfg["push"] if push is None else push

    site_root = cfg["site_root"]
    blog_dir = Path(site_root) / cfg["blog_dir"]
    if not blog_dir.is_dir():
        raise FileNotFoundError(f"site blog dir missing: {blog_dir}")

    post_path = blog_dir / f"{slug}.html"
    post_path.write_text(page_html)
    logger.info("unicorn: rendered %s -> %s", md_path, post_path)

    index_path = blog_dir / "index.html"
    index_text = index_path.read_text()
    search = build_search_terms(title, hook)
    new_index, card_status = insert_card(
        index_text, f"{slug}.html", title, hook, tags, search)
    if card_status in ("inserted", "updated"):
        index_path.write_text(new_index)

    rel_blog = cfg["blog_dir"]
    committed = pushed = False
    if commit:
        _git(site_root, "add", f"{rel_blog}/{slug}.html", f"{rel_blog}/index.html")
        status = _git(site_root, "status", "--porcelain",
                      f"{rel_blog}/{slug}.html", f"{rel_blog}/index.html")
        if status.strip():
            _git(site_root, "commit", "-m",
                 f"Publish blog: {title} (unicorn module)\n\n"
                 f"Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
            committed = True
            logger.info("unicorn: committed %s to %s", slug, site_root)
        if push:
            _git(site_root, "pull", "--rebase", "--autostash",
                 cfg["remote"], cfg["branch"])
            _git(site_root, "push", cfg["remote"], cfg["branch"])
            pushed = True
            logger.info("unicorn: pushed %s/%s", cfg["remote"], cfg["branch"])

    return {
        "status": "published" if pushed else "staged",
        "title": title,
        "slug": slug,
        "post_path": str(post_path),
        "index_card": card_status,
        "committed": committed,
        "pushed": pushed,
        "live_url": f"{cfg['site_base_url'].rstrip('/')}/{rel_blog}/{slug}.html",
    }
