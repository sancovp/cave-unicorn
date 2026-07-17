# cave-unicorn

<!-- SCALABLE-PUBLISHING:AUTOGEN START (managed block — do not edit between these markers) -->

![Stars](https://img.shields.io/github/stars/sancovp/cave-unicorn.svg?style=social) ![Updated](https://img.shields.io/badge/updated-2026_07_16-lightgrey.svg)

⭐ 1 stars • 🕑 Updated 2026-07-16

📦 Auto-published from the monorepo • [CHANGELOG](./CHANGELOG.md) • [sancovp/cave-unicorn](https://github.com/sancovp/cave-unicorn)

<!-- SCALABLE-PUBLISHING:AUTOGEN END -->

The UNICORN distribution module of the SANCREV SDK (an L9 cave-auxiliary lib,
same layer law as `cave-discord`): **connect produced blogs into the live
website** + **the setup interface for the distribution stack**.

UNICORN is the business game of CAVE ("Is the business side working?" —
`application/cave/ARCHITECTURE.md`). This module is its first concrete organ:
the pipe from the content the system already produces (the blog organ /
skill2framework chapters) onto the live site, run as a cave CronAutomation.

## What it connects

| side | what | where |
|---|---|---|
| producer | blog organ — `Blog_Request` nodes → markdown | `cave.core.publishing.blog_organ_nightly` |
| producer | skill2framework chapter blogs | `base/chaincompiler` skills / `chapters/` |
| site | the live blog (GitHub Pages) | `unicorn_config.json: site_root` (aisaac checkout) |

## The flow

```
Blog_Request {status: done, output_path: X.md, no site_published}
    → fire_site_publish (CronAutomation, nightly 02:37, after the 02:00 blog organ)
    → render X.md into the site's post skeleton  → {blog_dir}/{slug}.html
    → insert the blog-card into {blog_dir}/index.html (idempotent, count bumped)
    → git add/commit (+ pull --rebase --autostash + push when push=true)
    → flip the node: {site_published: true, site_url, site_published_at}
```

Blog markdown contract: first `# ` line = title; first `*...*` paragraph = the
hook/subtitle; the rest is the body (what the blog organ prompt already emits).

## Setup interface (v1 = the CLI)

```bash
cave-unicorn init                      # create $HEAVEN_DATA_DIR/unicorn_config.json
cave-unicorn show                      # print config
cave-unicorn set push true             # JSON-typed values
cave-unicorn publish path/to/blog1.md --tags "tool-eng context-eng" --no-push
cave-unicorn pending                   # done-but-unpublished Blog_Request nodes
cave-unicorn publish-pending --push    # publish them all
cave-unicorn enable-automation --push  # emit the CronAutomation hot-JSON schema
```

## The CAVE seam

`cave_unicorn.cave_seam` — import-if-present, identical law to
`cave_discord.cave_seam`: L7 (CAVE) consumes L9 (this lib), never the reverse.
`register_with_cave(cave_agent)` registers on a live agent's automation
registry; `emit_schema()` writes the schema JSON into the hot-reload
automations dir (`/tmp/heaven_data/automations/`) the Heart tick reads.

## The three organs (all E2E-proven 2026-07-10)

| organ | code_pointer | nightly | what it does |
|---|---|---|---|
| site publish | `cave_unicorn.publish.fire_site_publish` | 02:37 | Blog_Request done → live post + index card + push + Discord announce |
| socials pack | `cave_unicorn.socials.fire_socials_pack` | 03:07 | live blog → twitter/linkedin/discord posts + image prompts (heaven/minimax agent) |
| images | `cave_unicorn.images.fire_socials_images` | 03:37 | pack → hero/social-share/thumbnail PNGs (claude -p excalidraw agent, visually verified) |

Ready-to-post queue: `$HEAVEN_DATA_DIR/socials_queue/{slug}/` (pack.md + images/).

## Status markers

- IS (proven by `tests/test_unicorn.py`, 37 tests + the live E2E chain 2026-07-10):
  three blogs live on sancovp.github.io/aisaac/blog; a real Discord post via
  cave_discord; a verified socials pack; three verified PNGs — one piece of
  content flowed node → blog organ → site → posts → images hands-free.
- IS: all three automations emitted to the hot-reload dir (see the table).
- VISION (not built): web setup UI; posting the packs to external socials
  (Twitter/LinkedIn APIs — Isaac posts by hand from the queue for now); Skool leg.
