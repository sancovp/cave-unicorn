"""cave-unicorn CLI — the v1 setup interface for the distribution stack.

Commands:
  init                          create the unicorn config (setup step 0)
  show                          print the config
  set <key> <value>             set one config key (JSON values accepted)
  publish <md> [--slug --tags --month --push/--no-push]   publish one blog file
  pending                       list Blog_Request nodes done but not site-published
  publish-pending [--push/--no-push]                       publish all of those
  enable-automation [--schedule --push]                    emit the CronAutomation
                                schema into the hot-reload automations dir
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, List, Optional

from . import cave_seam, config, publish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _parse_value(raw: str) -> Any:
    # Deliberate coercion, not error-swallowing: a value that parses as JSON is
    # taken typed (true/3/["a"]); anything else is the literal string.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2))


def _split_tags(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    return [t for t in raw.replace(",", " ").split() if t]


def _cmd_init(args: argparse.Namespace) -> int:
    _print(config.init_config(force=args.force))
    return 0


def _cmd_show(_args: argparse.Namespace) -> int:
    _print(config.load_config())
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    _print(config.set_key(args.key, _parse_value(args.value)))
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    link_map = None
    if args.link:
        link_map = dict(pair.split("=", 1) for pair in args.link)
    report = publish.fire_site_publish(
        md_path=args.md_path, slug=args.slug, tags=_split_tags(args.tags),
        month=args.month, push=args.push,
        title=args.title, hook=args.hook, link_map=link_map,
    )
    _print(report)
    return 0 if report.get("status") in ("published", "staged") else 1


def _cmd_pending(_args: argparse.Namespace) -> int:
    graph, _set_props, query_props = publish._carton()
    if graph is None:
        _print({"status": "no_connection"})
        return 1
    _print(publish._unpublished_done_blogs(query_props, graph))
    return 0


def _cmd_publish_pending(args: argparse.Namespace) -> int:
    report = publish.fire_site_publish(push=args.push)
    _print(report)
    return 0 if report.get("status") in ("done", "no_pending") else 1


def _cmd_enable_automation(args: argparse.Namespace) -> int:
    paths = []
    if args.which in ("site", "all"):
        code_args = {"push": True} if args.push else {}
        paths.append(cave_seam.emit_schema(schedule=args.schedule,
                                           code_args=code_args))
    if args.which in ("socials", "all"):
        paths.append(cave_seam.emit_spec(cave_seam.build_socials_pack_automation()))
    if args.which in ("images", "all"):
        paths.append(cave_seam.emit_spec(cave_seam.build_socials_images_automation()))
    _print({"status": "emitted", "paths": paths})
    return 0


def _cmd_render_images(args: argparse.Namespace) -> int:
    from . import images
    kwargs = {}
    if args.pack_path:
        kwargs = {"pack_path": args.pack_path,
                  "blog_md_path": args.blog_md_path or "",
                  "out_dir": args.out_dir}
    report = images.fire_socials_images(**kwargs)
    _print(report)
    return 0 if report.get("status") in ("done", "rendered", "no_pending") else 1


def _cmd_pack_socials(args: argparse.Namespace) -> int:
    from . import socials
    kwargs = {}
    if args.md_path:
        kwargs = {"md_path": args.md_path, "live_url": args.live_url or "",
                  "slug": args.slug,
                  "journey_source": args.journey_source or "",
                  "existing_core": args.existing_core or ""}
    report = socials.fire_socials_pack(**kwargs)
    _print(report)
    return 0 if report.get("status") in ("done", "packed", "no_pending") else 1


def _cmd_socials_pending(_args: argparse.Namespace) -> int:
    from . import socials
    graph, _sp, _q = publish._carton()
    if graph is None:
        _print({"status": "no_connection"})
        return 1
    _print(socials._unpacked_published(graph))
    return 0


def _add_push_flags(p: argparse.ArgumentParser) -> None:
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--push", dest="push", action="store_true", default=None)
    grp.add_argument("--no-push", dest="push", action="store_false")


def _add_config_commands(sub) -> None:
    p_init = sub.add_parser("init", help="create the unicorn config")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=_cmd_init)

    sub.add_parser("show", help="print the config").set_defaults(func=_cmd_show)

    p_set = sub.add_parser("set", help="set one config key")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.set_defaults(func=_cmd_set)


def _add_site_commands(sub) -> None:
    p_pub = sub.add_parser("publish", help="publish one blog markdown file")
    p_pub.add_argument("md_path")
    p_pub.add_argument("--slug")
    p_pub.add_argument("--tags", help="space/comma separated index-card tags")
    p_pub.add_argument("--month")
    p_pub.add_argument("--title", help="override the title extracted from the md")
    p_pub.add_argument("--hook", help="override/supply the subtitle hook")
    p_pub.add_argument("--link", action="append",
                       help="rewrite a md link target: OLD=NEW (repeatable)")
    _add_push_flags(p_pub)
    p_pub.set_defaults(func=_cmd_publish)

    sub.add_parser("pending",
                   help="list done-but-unpublished Blog_Request nodes"
                   ).set_defaults(func=_cmd_pending)

    p_pp = sub.add_parser("publish-pending", help="publish all pending done blogs")
    _add_push_flags(p_pp)
    p_pp.set_defaults(func=_cmd_publish_pending)


def _add_socials_and_automation_commands(sub) -> None:
    p_auto = sub.add_parser("enable-automation",
                            help="emit CronAutomation schema(s) (hot-reload dir)")
    p_auto.add_argument("--schedule", default=cave_seam.DEFAULT_SCHEDULE)
    p_auto.add_argument("--push", action="store_true",
                        help="site automation publishes with push=true")
    p_auto.add_argument("--which", choices=["site", "socials", "images", "all"],
                        default="site")
    p_auto.set_defaults(func=_cmd_enable_automation)

    p_img = sub.add_parser("render-images",
                           help="render socials-pack images (scan, or one --pack-path)")
    p_img.add_argument("--pack-path", dest="pack_path")
    p_img.add_argument("--blog-md-path", dest="blog_md_path")
    p_img.add_argument("--out-dir", dest="out_dir")
    p_img.set_defaults(func=_cmd_render_images)

    p_pack = sub.add_parser("pack-socials",
                            help="generate socials packs (scan, or one --md-path)")
    p_pack.add_argument("--md-path", dest="md_path")
    p_pack.add_argument("--live-url", dest="live_url")
    p_pack.add_argument("--slug")
    p_pack.add_argument("--journey-source", dest="journey_source",
                        help="deep source paths (comma-separated) the agent reads")
    p_pack.add_argument("--existing-core", dest="existing_core",
                        help="persisted journey_core.json to reuse (fill once)")
    p_pack.set_defaults(func=_cmd_pack_socials)

    sub.add_parser("socials-pending",
                   help="list live blogs with no socials pack yet"
                   ).set_defaults(func=_cmd_socials_pending)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cave-unicorn",
                                     description="UNICORN distribution module CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_config_commands(sub)
    _add_site_commands(sub)
    _add_socials_and_automation_commands(sub)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
