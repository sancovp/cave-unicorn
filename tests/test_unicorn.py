"""cave-unicorn unit tests — render/split/index/config/seam/CLI, no network/git."""

import json
import re
from pathlib import Path

import pytest

from cave_unicorn import cli, config
from cave_unicorn.announce import announce_posts
from cave_unicorn.cave_seam import build_site_publish_automation, emit_schema
from cave_unicorn.site import (
    build_search_terms,
    insert_card,
    publish_file,
    render_post,
    slugify,
    split_front,
)

BLOG_MD = """# skilltree — the story

*My skills all loaded at once every turn — so I stopped loading the pile.*

## Where I was

Some body text with **bold** and a [link](https://example.com).

- a list item
"""

INDEX_FIXTURE = """<link rel="stylesheet" href="blog-style.css">
<div id="isaac-site">
  <article>
    <div class="result-count" id="count">2 posts</div>
    <div style="display:grid;gap:1rem;" id="posts">

      <a href="existing.html" class="blog-card" data-tags="cave" data-search="existing"><h3>Existing</h3><p>Hook.</p><span class="read-link">Read &rarr;</span></a>
    </div>
  </article>
</div>
"""


class TestSplitFront:
    def test_extracts_title_hook_body(self):
        title, hook, body = split_front(BLOG_MD)
        assert title == "skilltree — the story"
        assert hook.startswith("My skills all loaded")
        assert "# skilltree" not in body
        assert "*My skills" not in body
        assert "## Where I was" in body

    def test_no_title_raises(self):
        with pytest.raises(ValueError, match="no '# ' title heading"):
            split_front("just text\n")

    def test_no_hook_is_empty(self):
        title, hook, body = split_front("# T\n\nPlain first para.\n")
        assert title == "T" and hook == "" and "Plain first para." in body

    def test_bold_hook_strips_all_asterisks(self):
        title, hook, _ = split_front("# T\n\n**Bold hook line.**\n\nBody.\n")
        assert hook == "Bold hook line."
        assert "*" not in hook


class TestSlugify:
    def test_basic(self):
        assert slugify("skilltree — the story") == "skilltree-the-story"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty slug"):
            slugify("—")


class TestRenderPost:
    def test_skeleton_and_body(self):
        title, hook, page = render_post(BLOG_MD, month="July 2026")
        assert '<div class="post-tag">July 2026</div>' in page
        assert "<h1>skilltree — the story</h1>" in page
        assert 'class="post-subtitle"' in page
        assert "<strong>bold</strong>" in page
        assert 'href="https://example.com"' in page
        assert "sticky-cta.js" in page
        assert "blog-cta" in page

    def test_title_hook_overrides(self):
        title, hook, page = render_post(BLOG_MD, month="July 2026",
                                        title="Override", hook="Custom hook")
        assert title == "Override" and "<h1>Override</h1>" in page
        assert "Custom hook" in page


class TestInsertCard:
    def test_inserts_at_top_and_bumps_count(self):
        new, status = insert_card(INDEX_FIXTURE, "new-post.html", "New Post",
                                  "The hook.", ["tool-eng"], "new post hook")
        assert status == "inserted"
        assert '3 posts' in new
        # New card sits before the existing one.
        assert new.index('href="new-post.html"') < new.index('href="existing.html"')
        assert 'data-tags="tool-eng"' in new

    def test_idempotent(self):
        once, _ = insert_card(INDEX_FIXTURE, "new-post.html", "New Post",
                              "The hook.", [], "x")
        twice, status = insert_card(once, "new-post.html", "New Post",
                                    "The hook.", [], "x")
        assert status == "already_indexed" and twice == once

    def test_republish_updates_card_in_place(self):
        once, _ = insert_card(INDEX_FIXTURE, "new-post.html", "New Post",
                              "Old hook.", [], "x")
        updated, status = insert_card(once, "new-post.html", "New Post",
                                      "Better hook.", ["cave"], "x")
        assert status == "updated"
        assert "Better hook." in updated and "Old hook." not in updated
        assert updated.count('href="new-post.html"') == 1
        assert "3 posts" in updated  # count NOT double-bumped

    def test_missing_grid_raises(self):
        with pytest.raises(ValueError, match="posts"):
            insert_card("<html></html>", "a.html", "A", "h", [], "s")


class TestSearchTerms:
    def test_dedup_lowercase(self):
        s = build_search_terms("SkillTree Story", "the story of skilltree")
        words = s.split()
        assert "skilltree" in words and "story" in words
        assert len(words) == len(set(words))


class TestConfig:
    def test_roundtrip_and_set(self, tmp_path):
        p = str(tmp_path / "unicorn_config.json")
        cfg = config.init_config(path=p, site_root="/tmp/site")
        assert cfg["site_root"] == "/tmp/site"
        assert config.load_config(path=p)["blog_dir"] == "blog"
        cfg2 = config.set_key("push", True, path=p)
        assert cfg2["push"] is True

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="cave-unicorn init"):
            config.load_config(path=str(tmp_path / "nope.json"))

    def test_init_refuses_clobber(self, tmp_path):
        p = str(tmp_path / "c.json")
        config.init_config(path=p)
        with pytest.raises(FileExistsError):
            config.init_config(path=p)

    def test_set_unknown_key_raises(self, tmp_path):
        p = str(tmp_path / "c.json")
        config.init_config(path=p)
        with pytest.raises(KeyError, match="unknown unicorn config key"):
            config.set_key("bogus", 1, path=p)


class TestPublishFile:
    def _site(self, tmp_path):
        blog = tmp_path / "site" / "blog"
        blog.mkdir(parents=True)
        (blog / "index.html").write_text(INDEX_FIXTURE)
        md = tmp_path / "blog1.md"
        md.write_text(BLOG_MD)
        cfg = dict(config.DEFAULTS, site_root=str(tmp_path / "site"), push=False)
        return blog, md, cfg

    def test_publish_no_git(self, tmp_path):
        blog, md, cfg = self._site(tmp_path)
        report = publish_file(str(md), cfg, tags=["tool-eng"],
                              month="July 2026", commit=False)
        assert report["status"] == "staged" and not report["pushed"]
        post = blog / "skilltree-the-story.html"
        assert post.exists() and "<h1>skilltree — the story</h1>" in post.read_text()
        idx = (blog / "index.html").read_text()
        assert 'href="skilltree-the-story.html"' in idx and "3 posts" in idx
        assert report["live_url"].endswith("/blog/skilltree-the-story.html")

    def test_missing_blog_dir_raises(self, tmp_path):
        _blog, md, cfg = self._site(tmp_path)
        cfg["blog_dir"] = "nonexistent"
        with pytest.raises(FileNotFoundError, match="site blog dir missing"):
            publish_file(str(md), cfg, commit=False)

    def test_republish_writes_updated_card_to_disk(self, tmp_path):
        # Regression: the index write was gated on "inserted", so an "updated"
        # card was reported but silently never written (live bug 2026-07-10).
        blog, md, cfg = self._site(tmp_path)
        publish_file(str(md), cfg, month="July 2026", commit=False)
        publish_file(str(md), cfg, month="July 2026", commit=False,
                     hook="A brand new hook.")
        idx = (blog / "index.html").read_text()
        assert "A brand new hook." in idx

    def test_commit_refuses_wrong_branch(self, tmp_path):
        # Regression: commit lands on the CHECKED-OUT branch while push targets
        # cfg["branch"], so publishing from a work-branch checkout stranded the
        # commit and no-op-pushed stale main, reporting ok (live bug 2026-07-12).
        import subprocess
        blog, md, cfg = self._site(tmp_path)
        site_root = str(tmp_path / "site")
        def git(*args):
            subprocess.run(["git", "-C", site_root, *args], check=True,
                           capture_output=True)
        git("init", "-b", cfg["branch"])
        git("config", "user.email", "t@t"); git("config", "user.name", "t")
        git("add", "-A"); git("commit", "-m", "init")
        git("checkout", "-b", "some-work-branch")
        with pytest.raises(RuntimeError, match="not the configured publish branch"):
            publish_file(str(md), cfg, month="July 2026", commit=True, push=False)
        log = subprocess.run(["git", "-C", site_root, "log", "--oneline"],
                             capture_output=True, text=True).stdout
        assert "Publish blog" not in log  # nothing was committed

    def test_hook_override_and_link_map(self, tmp_path):
        blog, md, cfg = self._site(tmp_path)
        md.write_text("# Deep Dive\n\nSee [the story](./blog1.md) first.\n")
        report = publish_file(str(md), cfg, commit=False,
                              hook="Supplied hook.",
                              link_map={"./blog1.md": "the-story.html"})
        page = (blog / "deep-dive.html").read_text()
        assert "Supplied hook." in page
        assert 'href="the-story.html"' in page and "blog1.md" not in page
        idx = (blog / "index.html").read_text()
        assert "Supplied hook." in idx
        assert report["status"] == "staged"


class TestAnnounce:
    def test_disabled_skips(self):
        out = announce_posts([{"title": "T", "live_url": "u"}],
                             {"discord_announce": False})
        assert out == {"status": "skipped", "reason": "discord_announce disabled"}

    def test_empty_reports_skip(self):
        out = announce_posts([], {"discord_announce": True})
        assert out["status"] == "skipped"

    def test_missing_channel_fails_without_raising(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HEAVEN_DATA_DIR", str(tmp_path))
        (tmp_path / "discord_config.json").write_text(
            json.dumps({"token": "t", "guild_id": "g", "channels": {}}))
        out = announce_posts([{"title": "T", "live_url": "u"}],
                             {"discord_announce": True, "discord_channel": "nope"})
        assert out["status"] == "failed" and "nope" in out["error"]


class TestImages:
    def test_build_prompt_fills(self):
        from cave_unicorn import images
        p = images.build_prompt("/q/pack.md", "/x/blog.md", "/q/images")
        assert "/q/pack.md" in p and "/q/images" in p
        assert "render.py" in p and "{pack_path}" not in p

    def test_render_verifies_artifacts_not_report(self, tmp_path, monkeypatch):
        from cave_unicorn import images
        pack = tmp_path / "pack.md"
        pack.write_text("## IMAGE PROMPTS\nx\n")
        # Agent claims ok but renders nothing -> failed with the missing list.
        monkeypatch.setattr(images, "run_claude_agent",
                            lambda *a, **k: {"ok": True, "error": ""})
        out = images.render_for_pack(str(pack), "/x/blog.md")
        assert out["status"] == "failed" and "hero.png" in out["error"]

    def test_render_success_when_pngs_exist(self, tmp_path, monkeypatch):
        from cave_unicorn import images
        pack = tmp_path / "pack.md"
        pack.write_text("## IMAGE PROMPTS\nx\n")

        def fake_agent(prompt, timeout=900):
            for n in images.EXPECTED_PNGS:
                (tmp_path / "images" / n).write_bytes(b"png")
            return {"ok": True, "error": ""}

        monkeypatch.setattr(images, "run_claude_agent", fake_agent)
        out = images.render_for_pack(str(pack), "/x/blog.md")
        assert out["status"] == "rendered" and len(out["images"]) == 3

    def test_render_accepts_queue_dir_as_pack_path(self, tmp_path, monkeypatch):
        # Passing the per-slug queue DIR (operator habit) must resolve to
        # dir/pack.md and render into dir/images — not the dir's PARENT
        # (the live 2026-07-11 miss: PNGs landed in socials_queue/images).
        from cave_unicorn import images
        (tmp_path / "pack.md").write_text("## IMAGE PROMPTS\nx\n")

        def fake_agent(prompt, timeout=900):
            for n in images.EXPECTED_PNGS:
                (tmp_path / "images" / n).write_bytes(b"png")
            return {"ok": True, "error": ""}

        monkeypatch.setattr(images, "run_claude_agent", fake_agent)
        out = images.render_for_pack(str(tmp_path), "/x/blog.md")
        assert out["status"] == "rendered"
        assert out["images_dir"] == str(tmp_path / "images")

    def test_render_missing_pack_fails_loud(self, tmp_path):
        from cave_unicorn import images
        out = images.render_for_pack(str(tmp_path / "nope"), "/x/blog.md")
        assert out["status"] == "failed" and "pack not found" in out["error"]


class TestSeam:
    def test_schema_shape_matches_live_registrations(self):
        spec = build_site_publish_automation(code_args={"push": True})
        assert set(spec) == {"name", "description", "schedule", "code_pointer",
                             "code_args", "one_shot", "priority", "tags", "enabled"}
        assert spec["code_pointer"] == "cave_unicorn.publish.fire_site_publish"
        assert spec["code_args"] == {"push": True}
        assert re.fullmatch(r"[\d*/, -]+", spec["schedule"])

    def test_emit_schema_writes_hot_json(self, tmp_path):
        path = emit_schema(automations_dir=str(tmp_path))
        data = json.loads(Path(path).read_text())
        assert data["name"] == "unicorn_site_publish"
        assert data["enabled"] is True

    def test_socials_automation_spec(self, tmp_path):
        from cave_unicorn.cave_seam import build_socials_pack_automation, emit_spec
        spec = build_socials_pack_automation()
        assert spec["code_pointer"] == "cave_unicorn.socials.fire_socials_pack"
        path = emit_spec(spec, automations_dir=str(tmp_path))
        assert json.loads(Path(path).read_text())["name"] == "unicorn_socials_pack"

    def test_video_automation_spec_shape(self):
        # The schema exists and matches the live registration shape — but it
        # is INERT: nothing auto-emits it (see test_enable_automation_all_
        # excludes_video below).
        from cave_unicorn.cave_seam import build_video_render_automation
        spec = build_video_render_automation()
        assert set(spec) == {"name", "description", "schedule", "code_pointer",
                             "code_args", "one_shot", "priority", "tags", "enabled"}
        assert spec["code_pointer"] == "cave_unicorn.video.fire_video_render"
        assert spec["name"] == "unicorn_video_render"
        assert re.fullmatch(r"[\d*/, -]+", spec["schedule"])


# Module-level (NOT nested in a test method): the spawn multiprocessing
# context pickles _child_target BY REFERENCE (module + qualname), so the
# child process re-imports this test module to find them — a local closure
# cannot be pickled. Mirrors test_blog_organ_nightly.py's _child_sleeper/
# _child_ok exactly (same class of dispatch, same test hazard).

def _video_child_ok(config_kwargs, prompt, max_tool_calls, result_path):
    import json as _json
    from pathlib import Path as _P
    _P(result_path).write_text(_json.dumps({"ok": True, "error": ""}))


def _video_child_records_model(config_kwargs, prompt, max_tool_calls, result_path):
    import json as _json
    from pathlib import Path as _P
    _P(result_path).write_text(_json.dumps(
        {"ok": True, "error": "", "seen_model": config_kwargs["model"]}))


def _video_child_checks_persona(config_kwargs, prompt, max_tool_calls, result_path):
    # ok only if the ANIMATOR persona actually reached the agent config's
    # system_prompt (child process — signal pass/fail through the result file)
    import json as _json
    from pathlib import Path as _P
    sp = config_kwargs.get("system_prompt", "")
    ok = ("animates every single" in sp and "/tmp/remotion-test" in sp
          and "NEVER develop or even use Remotion" in sp)
    _P(result_path).write_text(_json.dumps(
        {"ok": ok,
         "error": "" if ok else f"persona missing from system_prompt: {sp[:80]!r}"}))


def _video_child_sleeper(config_kwargs, prompt, max_tool_calls, result_path):
    import time as _t
    _t.sleep(120)  # simulates the wedged-IPC hang: never returns in time


class TestVideo:
    def test_build_prompt_fills(self):
        from cave_unicorn import video
        p = video.build_prompt("/x/blog.md", "/q/slug/images", "/q/slug/video")
        assert "/x/blog.md" in p and "/q/slug/images" in p and "/q/slug/video" in p
        assert "final.mp4" in p and "{blog_md_path}" not in p

    def test_render_freshness_gate_rejects_stale_artifact(self, tmp_path,
                                                          monkeypatch):
        # The blog organ's 2026-07-12 law carried over: a final.mp4 left by a
        # PRIOR run (mtime before this dispatch) must NOT pass — agent claims
        # ok, artifact is stale -> failed.
        import os
        from cave_unicorn import video
        blog = tmp_path / "blog.md"
        blog.write_text("# T\n\nBody.\n")
        out = tmp_path / "video"
        out.mkdir()
        stale = out / "final.mp4"
        stale.write_bytes(b"old mp4")
        old = stale.stat().st_mtime - 3600
        os.utime(stale, (old, old))
        monkeypatch.setattr(video, "run_heaven_agent",
                            lambda *a, **k: {"ok": True, "error": ""})
        report = video.render_video_for_blog(str(blog), out_dir=str(out))
        assert report["status"] == "failed"
        assert "not freshly written" in report["error"]

    def test_render_success_when_fresh_video_exists(self, tmp_path, monkeypatch):
        from cave_unicorn import video
        blog = tmp_path / "blog.md"
        blog.write_text("# T\n\nBody.\n")
        out = tmp_path / "video"

        def fake_agent(prompt, timeout=1):
            (out / "final.mp4").write_bytes(b"mp4")
            return {"ok": True, "error": ""}

        monkeypatch.setattr(video, "run_heaven_agent", fake_agent)
        report = video.render_video_for_blog(str(blog), out_dir=str(out))
        assert report["status"] == "rendered"
        assert report["video_path"] == str(out / "final.mp4")

    def test_out_dir_defaults_to_images_sibling(self, tmp_path, monkeypatch):
        # images land in <pack dir>/images; the video is its sibling
        # <pack dir>/video, so one slug's artifacts stay together.
        from cave_unicorn import video
        blog = tmp_path / "blog.md"
        blog.write_text("# T\n")
        pack = tmp_path / "queue" / "slug"
        images = pack / "images"
        images.mkdir(parents=True)

        def fake_agent(prompt, timeout=1):
            (pack / "video" / "final.mp4").write_bytes(b"mp4")
            return {"ok": True, "error": ""}

        monkeypatch.setattr(video, "run_heaven_agent", fake_agent)
        report = video.render_video_for_blog(str(blog), images_dir=str(images))
        assert report["status"] == "rendered"
        assert report["video_dir"] == str(pack / "video")

    def test_render_missing_blog_fails_loud(self, tmp_path):
        from cave_unicorn import video
        report = video.render_video_for_blog(str(tmp_path / "nope.md"))
        assert report["status"] == "failed" and "blog md not found" in report["error"]

    def test_missing_minimax_config_refuses(self, monkeypatch, tmp_path):
        # No journal_agent_config.json -> gate loudly, never fall back to
        # any other dispatch mechanism.
        from cave_unicorn import video
        monkeypatch.setattr(video, "MINIMAX_CONFIG_PATH", tmp_path / "missing.json")
        monkeypatch.delenv("VIDEO_ORGAN_MODEL", raising=False)
        res = video.run_heaven_agent("p", timeout=1)
        assert res["ok"] is False and "minimax model config missing" in res["error"]

    def test_video_organ_model_overrides_shared_config(self, monkeypatch):
        # VIDEO_ORGAN_MODEL overrides the shared WD journal_agent_config model
        # (mirrors blog organ's BLOG_ORGAN_MODEL override), passed through to
        # the child's config_kwargs. Plumbing only — proves the ENV -> config
        # wiring, not agent quality (that needs a real run; see rule 03 in
        # onionmorph/.claude/rules — run the app, don't mock the framework).
        from cave_unicorn import video
        monkeypatch.setattr(video, "_minimax_model_config",
                            lambda: {"model": "MiniMax-M2.7-highspeed",
                                     "extra_model_kwargs":
                                         {"anthropic_api_url": "https://fake.local"}})
        monkeypatch.setenv("VIDEO_ORGAN_MODEL", "MiniMax-M3")
        res = video.run_heaven_agent("p", timeout=5,
                                     _child_target=_video_child_records_model)
        assert res["ok"] is True

    def test_animator_persona_reaches_agent_system_prompt(self, monkeypatch):
        # Isaac 2026-07-13 (verbatim): "this has to be EXPLICIT in the system
        # prompt of the agent, as its core way its persona works." The child
        # fake fails the run unless the ANIMATOR persona + one-directory law +
        # skills-only law are IN config_kwargs["system_prompt"].
        from cave_unicorn import video
        monkeypatch.setattr(video, "_minimax_model_config",
                            lambda: {"model": "MiniMax-M2.7-highspeed",
                                     "extra_model_kwargs":
                                         {"anthropic_api_url": "https://fake.local"}})
        res = video.run_heaven_agent("p", timeout=5,
                                     _child_target=_video_child_checks_persona)
        assert res["ok"] is True, res["error"]

    def test_wall_clock_timeout_kills_hung_child(self, monkeypatch):
        # run_heaven_agent must NEVER hang forever — same wedged-IPC-read
        # hang class the blog organ's dispatch was fixed for 2026-07-12; only
        # the out-of-process kill catches it. Plumbing only.
        import time
        from cave_unicorn import video
        monkeypatch.setattr(video, "_minimax_model_config",
                            lambda: {"model": "fake-model",
                                     "extra_model_kwargs":
                                         {"anthropic_api_url": "https://fake.local"}})
        t0 = time.time()
        res = video.run_heaven_agent("p", timeout=3, _child_target=_video_child_sleeper)
        assert res["ok"] is False
        assert "wall-clock timeout" in res["error"] and "KILLED" in res["error"]
        assert time.time() - t0 < 60

    def test_scan_flips_video_properties(self, tmp_path, monkeypatch):
        # Scan mode: images_rendered node -> rendered -> flip video_rendered/
        # video_path (+ clear a stale video_error); failure -> flip video_error.
        from cave_unicorn import video

        monkeypatch.setattr(
            video, "render_video_for_blog",
            lambda md, images_dir="", out_dir=None:
                {"status": "rendered", "video_path": "/v/final.mp4",
                 "video_dir": "/v"})
        flips = []
        monkeypatch.setattr(
            video, "_carton",
            lambda: (object(),
                     lambda concept, props, mode="merge", shared_connection=None:
                         flips.append((concept, props)),
                     None))
        monkeypatch.setattr(
            video, "_images_without_video",
            lambda graph: [{"concept": "Blog_X",
                            "props": {"output_path": "/x/blog.md",
                                      "images_dir": "/q/slug/images",
                                      "video_error": "old failure"}}])
        out = video.fire_video_render()
        assert out["status"] == "done" and out["rendered"] == 1
        (concept, props), = flips
        assert concept == "Blog_X"
        assert props["video_rendered"] is True
        assert props["video_path"] == "/v/final.mp4"
        assert props["video_error"] == ""  # stale error cleared on success

    def test_scan_records_error_on_failure(self, monkeypatch):
        from cave_unicorn import video
        monkeypatch.setattr(
            video, "render_video_for_blog",
            lambda md, images_dir="", out_dir=None:
                {"status": "failed", "error": "boom", "video_path": ""})
        flips = []
        monkeypatch.setattr(
            video, "_carton",
            lambda: (object(),
                     lambda concept, props, mode="merge", shared_connection=None:
                         flips.append((concept, props)),
                     None))
        monkeypatch.setattr(
            video, "_images_without_video",
            lambda graph: [{"concept": "Blog_X",
                            "props": {"output_path": "/x/blog.md"}}])
        out = video.fire_video_render()
        assert out["status"] == "done" and out["failed"] == 1
        assert flips == [("Blog_X", {"video_error": "boom"})]


class TestSocials:
    def test_build_prompt_fills_placeholders(self):
        from cave_unicorn.socials import build_prompt
        p = build_prompt("/x/blog.md", "https://site/b.html", "my-slug", "/q/out")
        assert "/x/blog.md" in p and "https://site/b.html" in p and "/q/out" in p
        assert "{blog_md_path}" not in p and "{out_dir}" not in p
        assert "journey_core.json" in p and "AIDA" in p  # the contract rode along

    def test_slug_from_site_url(self):
        from cave_unicorn.socials import _slug_from
        assert _slug_from({"site_url": "https://s/blog/a-post.html"}, "N") == "a-post"
        assert _slug_from({}, "Node_Name") == "node_name"

    def test_pack_one_reports_failure_without_raising(self, tmp_path, monkeypatch):
        # No heaven/minimax in the test env -> run_agent fails -> pack_one
        # must return a failed dict, never raise.
        from cave_unicorn import socials
        monkeypatch.setenv("HEAVEN_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(socials, "run_agent",
                            lambda *a, **k: (False, "dispatch failed", "m"))
        out = socials.pack_one("/x/blog.md", "u", "slug")
        assert out["status"] == "failed" and "dispatch failed" in out["error"]

    def test_pack_one_checks_fills_not_report(self, tmp_path, monkeypatch):
        # Agent claims ok but writes no fills -> failed (artifact is the truth).
        from cave_unicorn import socials
        monkeypatch.setenv("HEAVEN_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(socials, "run_agent", lambda *a, **k: (True, "", "m"))
        out = socials.pack_one("/x/blog.md", "u", "slug")
        assert out["status"] == "failed" and "journey_core.json" in out["error"]

    def test_pack_one_enforces_canonical_core(self, tmp_path, monkeypatch):
        # Live-found 2026-07-11 (the release-scan run): the agent RETYPED the
        # existing core instead of copying it, corrupting nine fields
        # ("plah forest", "sancopv" — a broken URL). The module must enforce
        # the canonical core over whatever the agent wrote; the only
        # sanctioned change is blog_url = live_url when unset. The canonical
        # FILE itself is never written.
        from cave_unicorn import socials
        from cave_unicorn.journey_suite import field_contract
        monkeypatch.setenv("HEAVEN_DATA_DIR", str(tmp_path))
        contract = field_contract()
        core = {f: f"core {f} text." for f, d in contract["journey_core"].items()
                if d.startswith("REQUIRED")}
        core["hashtags"] = ["AI"]
        canonical = tmp_path / "blog.journey_core.json"
        canonical.write_text(json.dumps(core))
        blog = {f: f"blog {f} text." for f, d in contract["journey_blog"].items()
                if d.startswith("REQUIRED")}
        out_dir = tmp_path / "socials_queue" / "slug"

        def retyping_agent(prompt, name="x"):
            out_dir.mkdir(parents=True, exist_ok=True)
            corrupted = dict(core)
            corrupted["status_quo"] = "plah retyped garbage"
            (out_dir / "journey_core.json").write_text(json.dumps(corrupted))
            (out_dir / "journey_blog.json").write_text(json.dumps(blog))
            return (True, "", "m")
        monkeypatch.setattr(socials, "run_agent", retyping_agent)

        out = socials.pack_one(str(tmp_path / "blog.md"), "https://live/x.html",
                               "slug", existing_core=str(canonical))
        assert out["status"] == "packed"
        final = json.loads((out_dir / "journey_core.json").read_text())
        assert final["status_quo"] == core["status_quo"]      # canonical won
        assert "plah" not in json.dumps(final)
        assert final["blog_url"] == "https://live/x.html"     # sanctioned add
        assert json.loads(canonical.read_text()) == core      # source untouched
        assert "plah" not in Path(out["pack_path"]).read_text()

    def test_framework_ready_gate(self, tmp_path):
        # Isaac 2026-07-10 (archival law, fix queue item 1): no framework
        # links on the persisted core = not ready. Signal = deep_dive_url AND
        # plugin_url both present on the sibling journey_core.json.
        from cave_unicorn.socials import _framework_ready, _sibling_core
        md = tmp_path / "blog.md"
        md.write_text("x")
        assert _framework_ready(_sibling_core(str(md))) is False  # no core file
        core = tmp_path / "blog.journey_core.json"
        core.write_text(json.dumps({"plugin_url": "https://plug"}))
        assert _framework_ready(str(core)) is False  # deep_dive_url missing
        core.write_text(json.dumps({"plugin_url": "https://plug",
                                    "deep_dive_url": "https://deep"}))
        assert _framework_ready(str(core)) is True
        core.write_text("not json")
        assert _framework_ready(str(core)) is False  # unreadable = not ready

    def test_scan_gate_skips_dispatch_marks_framework_missing(self, tmp_path,
                                                              monkeypatch):
        # Scan mode must NOT dispatch the agent for a framework-less journey:
        # it flips framework_missing (no socials_packed, so the node retries
        # on later scans) and moves on.
        from cave_unicorn import socials

        def _no_dispatch(*a, **k):
            raise AssertionError("agent dispatched through the framework gate")
        monkeypatch.setattr(socials, "run_agent", _no_dispatch)

        md = tmp_path / "blog.md"
        md.write_text("x")  # no sibling core -> gate holds
        flips = []
        monkeypatch.setattr(
            socials, "_carton",
            lambda: (object(),
                     lambda concept, props, mode="merge", shared_connection=None:
                         flips.append((concept, props)),
                     None))
        monkeypatch.setattr(
            socials, "_unpacked_published",
            lambda graph: [{"concept": "Blog_X",
                            "props": {"output_path": str(md),
                                      "site_url": "https://s/blog/x.html"}}])
        out = socials.fire_socials_pack()
        assert out["status"] == "done" and out["packed"] == 0
        assert out["results"][0]["status"] == "framework_missing"
        assert flips == [("Blog_X", {"framework_missing": True})]

    def test_scan_release_clears_stale_hold_and_error_flags(self, tmp_path,
                                                            monkeypatch):
        # A node that was held (framework_missing) and failed once
        # (socials_pack_error) must come out of a SUCCESSFUL pack with both
        # stale flags cleared — a healthy packed node never carries them.
        from cave_unicorn import socials

        md = tmp_path / "blog.md"
        md.write_text("x")
        core = {"deep_dive_url": "https://s/blog/deep.html",
                "plugin_url": "https://github.com/x/y"}
        (tmp_path / "blog.journey_core.json").write_text(json.dumps(core))

        monkeypatch.setattr(
            socials, "pack_one",
            lambda *a, **k: {"status": "packed", "slug": "x",
                             "model": "m", "pack_path": "p",
                             "blog_aida": "b", "core_path": "c"})
        flips = []
        monkeypatch.setattr(
            socials, "_carton",
            lambda: (object(),
                     lambda concept, props, mode="merge", shared_connection=None:
                         flips.append((concept, props)),
                     None))
        monkeypatch.setattr(
            socials, "_unpacked_published",
            lambda graph: [{"concept": "Blog_X",
                            "props": {"output_path": str(md),
                                      "site_url": "https://s/blog/x.html",
                                      "framework_missing": True,
                                      "socials_pack_error": "old failure"}}])
        out = socials.fire_socials_pack()
        assert out["packed"] == 1
        (concept, props), = flips
        assert concept == "Blog_X"
        assert props["socials_packed"] is True
        assert props["framework_missing"] is False
        assert props["socials_pack_error"] == ""


class TestJourneySuite:
    def _fills(self, tmp_path):
        from cave_unicorn.journey_suite import field_contract
        contract = field_contract()
        core = {f: f"core {f} text." for f, d in contract["journey_core"].items()
                if d.startswith("REQUIRED")}
        core["hashtags"] = ["AI"]
        core["blog_url"] = "https://site/blog/x.html"
        blog = {f: f"blog {f} text." for f, d in contract["journey_blog"].items()
                if d.startswith("REQUIRED")}
        cp, bp = tmp_path / "core.json", tmp_path / "blog.json"
        cp.write_text(json.dumps(core))
        bp.write_text(json.dumps(blog))
        return cp, bp

    def test_contract_lists_both_models(self):
        from cave_unicorn.journey_suite import field_contract
        c = field_contract()
        assert "status_quo" in c["journey_core"]
        assert "hook_attention" in c["journey_blog"]
        assert c["journey_blog"]["hook_attention"].startswith("REQUIRED")

    def test_render_suite_end_to_end(self, tmp_path):
        # Isaac 2026-07-11 (run-3 user gate): mechanic slot names are NEVER
        # published headings — structure invisible, sales-letter flow.
        from cave_unicorn.journey_suite import render_suite
        cp, bp = self._fills(tmp_path)
        (tmp_path / "img.md").write_text("HERO: a diagram.\n")
        out = render_suite(str(cp), str(bp), str(tmp_path / "out"),
                           str(tmp_path / "img.md"))
        aida = Path(out["blog_aida"]).read_text()
        for scaffold in ("## The Hook", "## What This Is About",
                         "## My Journey With This", "## The Core Insight",
                         "## Let Me Show You", "## Let's Talk About This",
                         "## Take Action", "## Links"):
            assert scaffold not in aida
        assert "blog hook_attention text." in aida      # the hook IS the opening
        assert "**blog cta_attention text.**" in aida   # closing copy, bolded lead
        pack = Path(out["pack"]).read_text()
        assert "## TWITTER/X" in pack and "## LINKEDIN" in pack
        assert "## DISCORD" in pack and "HERO: a diagram." in pack
        assert Path(out["core"]).exists()

    def test_blog_closes_with_one_funnel_link(self, tmp_path):
        # Isaac 2026-07-11: the ending is CLOSING COPY ending in ONE funnel
        # link — "Not link to github, not link to xyz. Link to *funnel about
        # that thing*." Explicit funnel_url wins; else deep_dive then plugin
        # (interim until funnel pages exist).
        from cave_unicorn.journey_suite import render_suite
        cp, bp = self._fills(tmp_path)
        core = json.loads(cp.read_text())
        core["deep_dive_url"] = "https://site/blog/x-deep-dive.html"
        core["plugin_url"] = "https://github.com/org/plugin"
        cp.write_text(json.dumps(core))
        out = render_suite(str(cp), str(bp), str(tmp_path / "out"),
                           funnel_url="https://site/funnel/x.html")
        aida = Path(out["blog_aida"]).read_text()
        assert "**Start here: https://site/funnel/x.html**" in aida
        assert aida.count("**Start here:") == 1          # ONE funnel link
        # fallback chain when no explicit funnel:
        out2 = render_suite(str(cp), str(bp), str(tmp_path / "out2"))
        aida2 = Path(out2["blog_aida"]).read_text()
        assert "**Start here: https://site/blog/x-deep-dive.html**" in aida2

    def test_blog_no_funnel_line_when_core_has_no_links(self, tmp_path):
        from cave_unicorn.journey_suite import render_suite
        cp, bp = self._fills(tmp_path)
        out = render_suite(str(cp), str(bp), str(tmp_path / "out"))
        aida = Path(out["blog_aida"]).read_text()
        assert "**Start here:" not in aida

    def test_linkedin_render_regressions(self, tmp_path):
        # Live-found 2026-07-10: the old from_core interpolated a Python LIST
        # repr into the hook, and '#'-carrying fills double-marked hashtags.
        from cave_unicorn.journey_suite import render_suite
        cp, bp = self._fills(tmp_path)
        core = json.loads(cp.read_text())
        core["hook"] = "An authored hook sentence."
        core["hashtags"] = ["#docmirror", "aicoding"]
        cp.write_text(json.dumps(core))
        out = render_suite(str(cp), str(bp), str(tmp_path / "out"))
        pack = Path(out["pack"]).read_text()
        assert "An authored hook sentence." in pack
        assert "['" not in pack          # no list reprs
        assert "##" not in pack.replace("\n## ", "\n@@ ")  # no double hashtag marks
        assert "#docmirror #aicoding" in pack

    def test_render_suite_rejects_bad_fill(self, tmp_path):
        from cave_unicorn.journey_suite import render_suite
        cp = tmp_path / "core.json"
        cp.write_text(json.dumps({"journey_name": "only this"}))
        bp = tmp_path / "blog.json"
        bp.write_text(json.dumps({}))
        with pytest.raises(Exception, match="validation error|Field required"):
            render_suite(str(cp), str(bp), str(tmp_path / "out"))

    def _core_obj(self, **over):
        from cave_unicorn.journey_suite import field_contract, _load_fork_modules
        contract = field_contract()
        data = {f: f"core {f} text." for f, d in contract["journey_core"].items()
                if d.startswith("REQUIRED")}
        data["hashtags"] = ["AI"]
        data.update(over)
        core_mod, _r, _t, _f = _load_fork_modules()
        return core_mod.JourneyCore(**data)

    def test_chapter_render_no_mechanic_headings(self):
        # Isaac 2026-07-11 (composed-run gate): the fork renderer's fixed slot
        # names + emoji link lines are the rejected scaffolding class — the
        # chapter render uses STORY-BEAT headings and closing copy instead.
        from cave_unicorn.journey_suite import render_chapter_blog
        core = self._core_obj(hook="An authored hook.")
        md = render_chapter_blog(core)
        for scaffold in ("## The Story", "## The Key Insight", "## Demo",
                         "## Why This Matters", "## Take Action",
                         "📖 Deep dive:", "🔌 Plugin:", "🛠️",
                         "If this helped, share it"):
            assert scaffold not in md
        for beat in ("## Where I was", "## The wall", "## The turn",
                     "## The boon"):
            assert beat in md
        assert "**An authored hook.**" in md
        assert "**core accomplishment text.**" in md   # result bolded in-beat

    def test_chapter_render_authored_headings_cta_and_funnel(self):
        # Agent-authored beat headings override the defaults; cta_copy is the
        # closing copy (carries the four facts + woven links); ONE funnel link
        # with the explicit-wins-then-deep-dive-then-plugin chain.
        from cave_unicorn.journey_suite import render_chapter_blog
        core = self._core_obj(
            deep_dive_url="https://site/blog/x-deep-dive.html",
            plugin_url="https://github.com/org/plugin")
        md = render_chapter_blog(
            core,
            beat_headings={"status_quo": "Before the machine existed"},
            cta_copy="This is a framework you hand your agents — the copy.",
            funnel_url="https://site/funnel/x.html")
        assert "## Before the machine existed" in md
        assert "## The wall" in md                      # unoverridden default
        assert "This is a framework you hand your agents — the copy." in md
        assert "**Start here: https://site/funnel/x.html**" in md
        assert md.count("**Start here:") == 1
        md2 = render_chapter_blog(core)                 # fallback chain
        assert "**Start here: https://site/blog/x-deep-dive.html**" in md2

    def test_chapter_render_no_funnel_when_core_has_no_links(self):
        from cave_unicorn.journey_suite import render_chapter_blog
        md = render_chapter_blog(self._core_obj())
        assert "**Start here:" not in md

    def _fixpoint_core(self, **over):
        fills = dict(
            hook="An authored hook.",
            overview_pain="core overview_pain text.",
            overview_solution="core overview_solution text.",
            overview_dream="core overview_dream text.",
            debate="core debate text.", trials="core trials text.",
            new_view="core new_view text.", right_way="core right_way text.",
            world_of_mastery="core world_of_mastery text.",
            framework_statement="core framework_statement text.",
            build_time="under a day",
            github_url="https://github.com/org/thing")
        fills.update(over)
        return self._core_obj(**fills)

    def test_fixpoint_post_structure_is_explicit(self):
        # Isaac 2026-07-12 (verbatim spec): ONE invariant format — OVERVIEW +
        # JOURNEY + FRAMEWORK, the seven plain-English stage headings repeating
        # in every post. Isaac 2026-07-12 (later, verbatim): the spine line +
        # "— crossing →" arrow markers are "weird as fuck ... assuming the user
        # knows something they dont" — notation is BANNED from the render; the
        # repetition of the headings is what teaches the format.
        from cave_unicorn.journey_suite import render_fixpoint_post
        md = render_fixpoint_post(self._fixpoint_core(),
                                  funnel_url="https://site/funnel/x.html")
        for section in ("## OVERVIEW", "## THE JOURNEY", "## THE FRAMEWORK"):
            assert section in md
        for stage in ("### STATUS QUO", "### THE DEBATE", "### THE TRIALS",
                      "### THE NEW VIEW", "### THE RIGHT WAY", "### THE BOON",
                      "### THE WORLD OF MASTERY"):
            assert stage in md
        for notation in ("*— crossing →*", "*— obstacles →*", "*— testing →*",
                         "*— systematize →*", "*— return →*",
                         "*STATUS QUO → THE DEBATE —crossing→"):
            assert notation not in md   # cryptic format vocabulary never renders
        assert "**The pain:**" in md and "**My solution:**" in md \
            and "**The dream:**" in md
        # Dream before solution ALWAYS (Isaac 2026-07-12, verbatim: "nobody
        # cares how the plane works they care about hawaii") — pain hooks,
        # dream sells, the solution is the ticket and comes LAST.
        assert md.index("**The pain:**") < md.index("**The dream:**") \
            < md.index("**My solution:**")
        assert "**We solved this.**" in md

    def test_fixpoint_links_are_real_anchors(self):
        # Live-found 2026-07-12: bare URLs never autolink on the site — every
        # link must be a markdown anchor, and the funnel close is a LINK.
        from cave_unicorn.journey_suite import render_fixpoint_post
        core = self._fixpoint_core(
            deep_dive_url="https://site/blog/x-global.html")
        md = render_fixpoint_post(core, funnel_url="https://site/funnel/x.html")
        assert "[github.com/org/thing](https://github.com/org/thing)" in md
        assert "[the global view](https://site/blog/x-global.html)" in md
        assert "**[Start here](https://site/funnel/x.html)**" in md
        assert "**Start here: http" not in md          # the dead-text form is banned
        assert md.count("[Start here]") == 1

    def test_fixpoint_fails_loud_on_missing_fields(self):
        from cave_unicorn.journey_suite import render_fixpoint_post
        with pytest.raises(ValueError, match="trials"):
            render_fixpoint_post(self._fixpoint_core(trials=None))

    def test_receipts_section_renders_when_proof_slots_filled(self):
        # GAS proof slots (Isaac 2026-07-13 phase-A: "even just copying the
        # proof slots will help"): claim + receipted premises + theme render
        # as a visible THE RECEIPTS section between JOURNEY and FRAMEWORK.
        from cave_unicorn.journey_suite import render_fixpoint_post
        core = self._fixpoint_core(
            grand_argument_claim="An overnight content chain is buildable.",
            premises=["The organs fired nightly|the 2026-07-12 blog run",
                      "The posts went live untouched|the site commit log"],
            theme="In order to publish daily, you must learn to trust "
                  "gated automation.")
        md = render_fixpoint_post(core)
        assert "## THE RECEIPTS" in md
        assert "**The claim:** An overnight content chain is buildable." in md
        assert "- The organs fired nightly — *receipt:* the 2026-07-12 blog run" in md
        assert "**The lesson:** In order to publish daily" in md
        # placement: after the journey, before the framework close
        assert md.index("## THE JOURNEY") < md.index("## THE RECEIPTS") \
            < md.index("## THE FRAMEWORK")

    def test_receipts_section_absent_when_slots_absent(self):
        # absent = section absent — no fallbacks, no empty heading.
        from cave_unicorn.journey_suite import render_fixpoint_post
        md = render_fixpoint_post(self._fixpoint_core())
        assert "THE RECEIPTS" not in md and "**The claim:**" not in md

    def test_receipts_partial_fill_fails_loud(self):
        from cave_unicorn.journey_suite import render_fixpoint_post
        with pytest.raises(ValueError, match="partially filled.*premises"):
            render_fixpoint_post(self._fixpoint_core(
                grand_argument_claim="A claim with no premises."))
        # theme floating alone is also a partial proof fill
        with pytest.raises(ValueError, match="partially filled"):
            render_fixpoint_post(self._fixpoint_core(
                theme="In order to X, you must learn Y."))

    def test_receipts_malformed_premise_fails_loud(self):
        from cave_unicorn.journey_suite import render_fixpoint_post
        with pytest.raises(ValueError, match="malformed premise"):
            render_fixpoint_post(self._fixpoint_core(
                grand_argument_claim="A claim.",
                premises=["a premise with no receipt separator"]))


class TestCli:
    def test_init_show_set(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HEAVEN_DATA_DIR", str(tmp_path))
        assert cli.main(["init"]) == 0
        assert cli.main(["set", "push", "true"]) == 0
        assert cli.main(["show"]) == 0
        out = capsys.readouterr().out
        assert '"push": true' in out

    def test_publish_via_cli(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HEAVEN_DATA_DIR", str(tmp_path))
        blog = tmp_path / "site" / "blog"
        blog.mkdir(parents=True)
        (blog / "index.html").write_text(INDEX_FIXTURE)
        md = tmp_path / "b.md"
        md.write_text(BLOG_MD)
        cli.main(["init"])
        cli.main(["set", "site_root", str(tmp_path / "site")])
        # --no-push publishes files + local commit only; the fixture site is not
        # a git repo, so commit must fail loudly -> CLI reports failed (rc 1).
        assert cli.main(["publish", str(md), "--no-push"]) == 1

    def test_enable_automation(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CAVE_AUTOMATIONS_DIR", str(tmp_path))
        assert cli.main(["enable-automation", "--push", "--which", "all"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert len(out["paths"]) == 3  # site + socials + images
        assert all(Path(p).exists() for p in out["paths"])

    def test_enable_automation_all_excludes_video(self, tmp_path, monkeypatch,
                                                  capsys):
        # INERT law (phase-A 2026-07-13): the video organ is enabled ONLY by
        # the explicit --which video hand; a routine --which all re-emit must
        # never flip it on as a side effect.
        monkeypatch.setenv("CAVE_AUTOMATIONS_DIR", str(tmp_path))
        assert cli.main(["enable-automation", "--which", "all"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert not any("video" in p for p in out["paths"])
        assert not (tmp_path / "unicorn_video_render.json").exists()
        assert cli.main(["enable-automation", "--which", "video"]) == 0
        out2 = json.loads(capsys.readouterr().out)
        assert out2["paths"] == [str(tmp_path / "unicorn_video_render.json")]
        data = json.loads((tmp_path / "unicorn_video_render.json").read_text())
        assert data["code_pointer"] == "cave_unicorn.video.fire_video_render"


# ── dispatch wall-clock timeout (the 2026-07-12 hang class) ──────────────────
# Stand-in child bodies live at MODULE level: the spawn context pickles the
# target by reference, so the child re-imports this test module to find them.

def _child_sleeper(config_kwargs, prompt, max_tool_calls, result_path):
    import time
    time.sleep(120)  # simulates the wedged-IPC hang: never returns in time


def _child_ok(config_kwargs, prompt, max_tool_calls, result_path):
    import json as _json
    from pathlib import Path as _P
    _P(result_path).write_text(_json.dumps({"ok": True, "error": ""}))


def _child_crash(config_kwargs, prompt, max_tool_calls, result_path):
    import os as _os
    _os._exit(3)  # dies without writing a result


class TestDispatchTimeout:
    """run_agent must NEVER hang forever: the live 2026-07-12 hang wedged a
    blocking IPC read ON the event-loop thread, so only the out-of-process
    kill (child process + parent deadline) can catch the class."""

    def _dispatch_mod(self, tmp_path, monkeypatch):
        import cave_unicorn.dispatch as dispatch
        cfg = tmp_path / "journal_agent_config.json"
        cfg.write_text(json.dumps({
            "model": "fake-model",
            "extra_model_kwargs": {"anthropic_api_url": "https://fake.local"}}))
        monkeypatch.setattr(dispatch, "MINIMAX_CONFIG_PATH", cfg)
        return dispatch

    def test_wall_clock_timeout_kills_hung_child(self, tmp_path, monkeypatch):
        import time
        dispatch = self._dispatch_mod(tmp_path, monkeypatch)
        t0 = time.time()
        ok, err, model = dispatch.run_agent(
            "x", timeout_s=3, _child_target=_child_sleeper)
        assert not ok
        assert "wall-clock timeout" in err and "KILLED" in err
        assert model == "fake-model"
        assert time.time() - t0 < 60  # killed at the deadline, not after 120s

    def test_child_result_roundtrip(self, tmp_path, monkeypatch):
        dispatch = self._dispatch_mod(tmp_path, monkeypatch)
        ok, err, model = dispatch.run_agent(
            "x", timeout_s=30, _child_target=_child_ok)
        assert ok and err == "" and model == "fake-model"

    def test_child_crash_is_reported_loudly(self, tmp_path, monkeypatch):
        dispatch = self._dispatch_mod(tmp_path, monkeypatch)
        ok, err, _model = dispatch.run_agent(
            "x", timeout_s=30, _child_target=_child_crash)
        assert not ok
        assert "without writing a result" in err and "code 3" in err
