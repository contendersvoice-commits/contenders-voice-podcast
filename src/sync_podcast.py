"""Main orchestrator: sync Substack written posts -> mastered MP3s -> Podcast RSS & HTML."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any
import urllib.parse
import urllib.request

from audio_engine import prepare_square_artwork, synthesize_and_master_mp3
from rss_builder import build_podcast_rss, build_web_player_html
from text_cleaner import (
    build_show_notes_html,
    build_spoken_chunks,
    clean_post_title,
    clean_substack_html,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
STATE_PATH = ROOT_DIR / "state" / "episodes.json"
DOCS_DIR = ROOT_DIR / "docs"
IGNORE_PATH = ROOT_DIR / "ignore_slugs.txt"
BUILD_DIR = ROOT_DIR / "build"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_ignored_slugs(path: Path) -> set[str]:
    if not path.exists():
        return set()
    slugs: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            # Allow users to paste a full URL or just a slug
            if "/p/" in cleaned:
                cleaned = cleaned.rstrip("/").split("/p/")[-1].split("?")[0]
            slugs.add(cleaned)
    return slugs


def _http_get_json(url: str, attempts: int = 3) -> Any:
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
            return json.loads(raw)
        except Exception as exc:
            last_err = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"GET {url} failed: {last_err}") from last_err


def fetch_newsletter_posts(subdomain: str) -> list[dict[str, Any]]:
    """Fetch all public written newsletter posts newest-first (skips podcasts to avoid loops)."""
    all_posts: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(25):
        params: dict[str, str] = {"sort": "new", "limit": "20"}
        if cursor:
            params["cursor"] = cursor
        url = f"https://{subdomain}.substack.com/api/v1/archive?{urllib.parse.urlencode(params)}"
        data = _http_get_json(url)
        posts = data.get("posts", []) if isinstance(data, dict) else data
        if not posts:
            break
        for post in posts:
            if post.get("type") == "newsletter" and post.get("audience") == "everyone":
                all_posts.append(post)
        cursor = data.get("nextCursor") if isinstance(data, dict) else None
        if not cursor:
            break
        time.sleep(0.25)
    return all_posts


def resolve_github_coords(settings: dict[str, Any]) -> tuple[str, str]:
    owner = settings.get("github_owner", "")
    repo = settings.get("github_repo", "contenders-voice-podcast")
    gh_env = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in gh_env and (not owner or owner == "REPLACE_WITH_GITHUB_USERNAME"):
        env_owner, env_repo = gh_env.split("/", 1)
        return env_owner, env_repo
    return owner, repo


def upload_to_github_release(mp3_path: Path, release_tag: str, owner: str, repo: str) -> str:
    """Upload MP3 to GitHub Release with --clobber and return direct download URL."""
    cmd = ["gh", "release", "upload", release_tag, str(mp3_path), "--clobber"]
    if owner and owner != "REPLACE_WITH_GITHUB_USERNAME":
        cmd.extend(["--repo", f"{owner}/{repo}"])
    subprocess.run(cmd, check=True)
    return f"https://github.com/{owner}/{repo}/releases/download/{release_tag}/{mp3_path.name}"


def _build_plain_summary(subtitle: str, cleaned_soup: Any, max_len: int = 240) -> str:
    if subtitle:
        return subtitle[:max_len]
    text = re.sub(r"\s+", " ", cleaned_soup.get_text(" ", strip=True)).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description="Sync Contender's Voice Substack to Podcast RSS.")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max new episodes to synthesize per run (default: 5; use 60+ to backfill all).",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--local-only",
        action="store_true",
        help="Run locally into build/preview/ without modifying state/episodes.json or docs/.",
    )
    mode_group.add_argument(
        "--publish-releases",
        action="store_true",
        help="Upload new MP3s to GitHub Release and update state/episodes.json + docs/.",
    )
    mode_group.add_argument(
        "--rebuild-only",
        action="store_true",
        help="Rebuild docs/podcast.xml and docs/index.html from existing state without TTS.",
    )
    args = parser.parse_args()

    settings = load_json(CONFIG_DIR / "settings.json")
    pronunciations = load_json(CONFIG_DIR / "pronunciations.json").get("replacements", {})
    ignored_slugs = load_ignored_slugs(IGNORE_PATH)
    owner, repo = resolve_github_coords(settings)
    base_pages_url = f"https://{owner}.github.io/{repo}"

    if args.local_only:
        preview_dir = BUILD_DIR / "preview"
        audio_dir = preview_dir / "audio"
        artwork_dir = preview_dir / "artwork"
        state_file = BUILD_DIR / "local_episodes.json"
        out_xml = preview_dir / "podcast.xml"
        out_html = preview_dir / "index.html"
        base_pages_url = preview_dir.resolve().as_uri()
    else:
        audio_dir = BUILD_DIR / "audio"
        artwork_dir = DOCS_DIR / "artwork"
        state_file = STATE_PATH
        out_xml = DOCS_DIR / "podcast.xml"
        out_html = DOCS_DIR / "index.html"

    state = load_json(state_file) if state_file.exists() else {"episodes": {}}
    episodes: dict[str, dict[str, Any]] = state.setdefault("episodes", {})

    # Always keep square 1400x1400 show logo artwork ready
    show_cover_path = artwork_dir / "show-cover.jpg"
    if not show_cover_path.exists():
        print("Preparing 1400x1400 show cover artwork...")
        prepare_square_artwork(settings["show_logo_source_url"], show_cover_path)

    if not args.rebuild_only:
        if args.publish_releases and (not owner or owner == "REPLACE_WITH_GITHUB_USERNAME"):
            raise RuntimeError(
                "github_owner is still REPLACE_WITH_GITHUB_USERNAME in config/settings.json "
                "and GITHUB_REPOSITORY is not set."
            )

        print(f"Fetching newsletter archive for {settings['substack_subdomain']}.substack.com...")
        all_posts = fetch_newsletter_posts(settings["substack_subdomain"])
        pending = [
            p
            for p in all_posts
            if p.get("slug")
            and p["slug"] not in episodes
            and p["slug"] not in ignored_slugs
        ]
        print(
            f"Found {len(all_posts)} written posts total; "
            f"{len(pending)} pending synthesis (limit={args.limit})."
        )

        to_process = pending[: max(0, args.limit)]
        for idx, summary_post in enumerate(to_process, 1):
            slug = summary_post["slug"]
            post_url = (
                summary_post.get("canonical_url")
                or f"https://{settings['substack_subdomain']}.substack.com/p/{slug}"
            )
            print(f"[{idx}/{len(to_process)}] Processing {slug}...")

            full_post = _http_get_json(
                f"https://{settings['substack_subdomain']}.substack.com/api/v1/posts/{slug}"
            )
            title = clean_post_title(full_post.get("title") or summary_post.get("title") or slug)
            subtitle = (full_post.get("subtitle") or summary_post.get("subtitle") or "").strip()
            pub_date = full_post.get("post_date") or summary_post.get("post_date") or ""
            year = pub_date[:4] if len(pub_date) >= 4 else ""
            raw_html = full_post.get("body_html") or ""
            cover_url = full_post.get("cover_image") or summary_post.get("cover_image") or ""

            cleaned_soup = clean_substack_html(raw_html)

            # Prepare square episode artwork (fallback to show cover if download fails)
            ep_art_path = artwork_dir / f"{slug}.jpg"
            has_ep_art = False
            if cover_url:
                try:
                    has_ep_art = prepare_square_artwork(cover_url, ep_art_path)
                except Exception as exc:
                    print(f"  Warning: could not process cover image for {slug} ({exc}); using show cover.")
            if not has_ep_art:
                shutil.copy2(show_cover_path, ep_art_path)

            if args.local_only:
                ep_art_url = f"artwork/{slug}.jpg"
            else:
                ep_art_url = f"{base_pages_url}/artwork/{slug}.jpg"

            # Prepare HTML show notes + spoken chunks
            content_html = build_show_notes_html(
                post_title=title,
                post_url=post_url,
                cleaned_soup=cleaned_soup,
                artwork_url=cover_url or ep_art_url,
            )
            body_chunks, outro_text = build_spoken_chunks(
                title=title,
                subtitle=subtitle,
                cleaned_soup=cleaned_soup,
                pronunciations=pronunciations,
            )

            mp3_path = audio_dir / f"{slug}.mp3"
            duration_sec, audio_bytes = synthesize_and_master_mp3(
                body_chunks=body_chunks,
                outro_text=outro_text,
                output_mp3=mp3_path,
                voice=settings["voice"],
                rate=settings["rate"],
                title=title,
                artist=settings["author"],
                album=settings["show_title"],
                year=year,
                artwork_path=ep_art_path,
                bitrate=settings["mp3_bitrate"],
                sample_rate=int(settings["sample_rate"]),
            )
            print(f"  Mastered MP3: {duration_sec}s, {audio_bytes / (1024*1024):.2f} MB")

            if args.publish_releases:
                audio_url = upload_to_github_release(
                    mp3_path, settings["release_tag"], owner, repo
                )
                mp3_path.unlink(missing_ok=True)
            else:
                audio_url = mp3_path.resolve().as_uri()

            episodes[slug] = {
                "slug": slug,
                "title": title,
                "subtitle": subtitle,
                "post_url": post_url,
                "pub_date": pub_date,
                "summary": _build_plain_summary(subtitle, cleaned_soup),
                "content_html": content_html,
                "audio_url": audio_url,
                "audio_bytes": audio_bytes,
                "duration_sec": duration_sec,
                "artwork_url": ep_art_url,
                "local_audio_rel": f"audio/{slug}.mp3",
                "local_artwork_rel": f"artwork/{slug}.jpg",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            save_json(state_file, state)
            time.sleep(0.4)

    rss_count = build_podcast_rss(
        settings=settings,
        episodes=episodes,
        ignored_slugs=ignored_slugs,
        base_pages_url=base_pages_url,
        output_xml_path=out_xml,
        show_cover_href="artwork/show-cover.jpg" if args.local_only else None,
        feed_self_href="podcast.xml" if args.local_only else None,
    )
    html_count = build_web_player_html(
        settings=settings,
        episodes=episodes,
        ignored_slugs=ignored_slugs,
        output_html_path=out_html,
        local_preview=args.local_only,
    )
    print(f"Built {out_xml} ({rss_count} episodes) and {out_html} ({html_count} episodes).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
