"""Main orchestrator: sync Substack written posts -> mastered MP3s -> Podcast RSS & HTML."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
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
import xml.etree.ElementTree as ET

try:
    from audio_engine import (
        USER_AGENT,
        decode_substack_cdn_url,
        prepare_square_artwork,
        synthesize_and_master_mp3,
    )
    from rss_builder import build_podcast_rss, build_web_player_html
    from text_cleaner import (
        build_show_notes_html,
        build_spoken_chunks,
        clean_post_title,
        clean_substack_html,
    )
except ImportError:
    from .audio_engine import (
        USER_AGENT,
        decode_substack_cdn_url,
        prepare_square_artwork,
        synthesize_and_master_mp3,
    )
    from .rss_builder import build_podcast_rss, build_web_player_html
    from .text_cleaner import (
        build_show_notes_html,
        build_spoken_chunks,
        clean_post_title,
        clean_substack_html,
    )

PIPELINE_VERSION = 2

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
STATE_PATH = ROOT_DIR / "state" / "episodes.json"
BACKFILL_QUEUE_PATH = ROOT_DIR / "state" / "backfill_queue.json"
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
            if "/p/" in cleaned:
                cleaned = cleaned.rstrip("/").split("/p/")[-1].split("?")[0]
            slugs.add(cleaned)
    return slugs


def _http_get_bytes(url: str, attempts: int = 3) -> bytes:
    last_err: Exception | None = None
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    }
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            return urllib.request.urlopen(req, timeout=20).read()
        except Exception as exc:
            last_err = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"GET {url} failed: {last_err}") from last_err


def _http_get_json(url: str, attempts: int = 3) -> Any:
    return json.loads(_http_get_bytes(url, attempts=attempts).decode("utf-8"))


def _slug_from_url(url: str) -> str:
    if "/p/" not in url:
        return ""
    return url.rstrip("/").split("/p/")[-1].split("?")[0]


def _pubdate_to_iso(pub_date_raw: str) -> str:
    try:
        dt = parsedate_to_datetime(pub_date_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_rss_newsletter_posts(subdomain: str) -> list[dict[str, Any]]:
    """Fetch newest written posts from Substack's official RSS /feed (skipping synced audio)."""
    rss_url = f"https://{subdomain}.substack.com/feed"
    rss_bytes = _http_get_bytes(rss_url)
    root = ET.fromstring(rss_bytes)
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}

    posts: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        link = (item.findtext("link") or "").strip()
        slug = _slug_from_url(link)
        if not slug:
            continue

        enclosure = item.find("enclosure")
        enc_type = (enclosure.get("type") or "") if enclosure is not None else ""
        enc_url = (enclosure.get("url") or "") if enclosure is not None else ""
        if enc_type.lower().startswith("audio/"):
            continue

        body_html = item.findtext("content:encoded", "", ns) or ""
        if "Audio edition of " in body_html and "Contender's Voice" in unescape(body_html):
            continue

        cover_image = ""
        if enc_type.lower().startswith("image/") and enc_url:
            cover_image = decode_substack_cdn_url(enc_url)
        else:
            img_match = re.search(r'<img[^>]+src="([^"]+)"', body_html)
            if img_match:
                cover_image = decode_substack_cdn_url(unescape(img_match.group(1)))

        posts.append(
            {
                "slug": slug,
                "title": unescape(item.findtext("title") or slug),
                "subtitle": unescape((item.findtext("description") or "").strip()),
                "post_date": _pubdate_to_iso((item.findtext("pubDate") or "").strip()),
                "post_url": link,
                "cover_image": cover_image,
                "body_html": body_html,
            }
        )
    return posts


def load_backfill_queue(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = load_json(path)
    return list(data.get("posts", []))


def export_full_archive_to_backfill(subdomain: str, dest_path: Path) -> int:
    """Export all public written posts locally via Substack's archive API for backfilling."""
    all_summaries: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(25):
        params: dict[str, str] = {"sort": "new", "limit": "20"}
        if cursor:
            params["cursor"] = cursor
        url = f"https://{subdomain}.substack.com/api/v1/archive?{urllib.parse.urlencode(params)}"
        data = _http_get_json(url)
        batch = data.get("posts", []) if isinstance(data, dict) else data
        if not batch:
            break
        for post in batch:
            if post.get("type") == "newsletter" and post.get("audience") == "everyone":
                all_summaries.append(post)
        cursor = data.get("nextCursor") if isinstance(data, dict) else None
        if not cursor:
            break
        time.sleep(0.25)

    exported: list[dict[str, Any]] = []
    for idx, summary in enumerate(all_summaries, 1):
        slug = summary.get("slug") or ""
        if not slug:
            continue
        print(f"  Exporting [{idx}/{len(all_summaries)}] {slug}...")
        full = _http_get_json(f"https://{subdomain}.substack.com/api/v1/posts/{slug}")
        cover = full.get("cover_image") or summary.get("cover_image") or ""
        exported.append(
            {
                "slug": slug,
                "title": full.get("title") or summary.get("title") or slug,
                "subtitle": (full.get("subtitle") or summary.get("subtitle") or "").strip(),
                "post_date": full.get("post_date") or summary.get("post_date") or "",
                "post_url": summary.get("canonical_url") or f"https://{subdomain}.substack.com/p/{slug}",
                "cover_image": decode_substack_cdn_url(cover) if cover else "",
                "body_html": full.get("body_html") or "",
            }
        )
        time.sleep(0.2)

    exported.sort(key=lambda p: p.get("post_date", ""), reverse=True)
    save_json(dest_path, {"posts": exported})
    return len(exported)


def collect_all_available_posts(subdomain: str) -> list[dict[str, Any]]:
    """Merge live RSS feed posts with seeded historical backfill posts, newest-first."""
    by_slug: dict[str, dict[str, Any]] = {}
    for post in load_backfill_queue(BACKFILL_QUEUE_PATH):
        if post.get("slug"):
            by_slug[post["slug"]] = post

    try:
        rss_posts = fetch_rss_newsletter_posts(subdomain)
        print(f"Live RSS feed fetched cleanly ({len(rss_posts)} posts).")
        for post in rss_posts:
            by_slug[post["slug"]] = post
    except Exception as exc:
        if not by_slug:
            raise
        print(
            f"Warning: live RSS fetch failed ({exc}); "
            f"continuing with {len(by_slug)} posts from state/backfill_queue.json."
        )

    merged = list(by_slug.values())
    merged.sort(key=lambda p: p.get("post_date", ""), reverse=True)
    return merged


def resolve_github_coords(settings: dict[str, Any]) -> tuple[str, str]:
    owner = settings.get("github_owner", "")
    repo = settings.get("github_repo", "contenders-voice-podcast")
    gh_env = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in gh_env and (not owner or owner == "REPLACE_WITH_GITHUB_USERNAME"):
        env_owner, env_repo = gh_env.split("/", 1)
        return env_owner, env_repo
    return owner, repo


def build_public_audio_url(
    filename: str,
    release_tag: str,
    owner: str,
    repo: str,
    audio_base_url: str = "",
) -> str:
    """Return the public podcast enclosure URL (iOS-friendly proxy when configured)."""
    base = (audio_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}/{filename}"
    return f"https://github.com/{owner}/{repo}/releases/download/{release_tag}/{filename}"


def upload_to_github_release(
    mp3_path: Path,
    release_tag: str,
    owner: str,
    repo: str,
    attempts: int = 4,
    audio_base_url: str = "",
) -> str:
    """Upload MP3 to GitHub Release with --clobber and return public enclosure URL."""
    cmd = ["gh", "release", "upload", release_tag, str(mp3_path), "--clobber"]
    if owner and owner != "REPLACE_WITH_GITHUB_USERNAME":
        cmd.extend(["--repo", f"{owner}/{repo}"])
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            subprocess.run(cmd, check=True)
            return build_public_audio_url(
                mp3_path.name,
                release_tag=release_tag,
                owner=owner,
                repo=repo,
                audio_base_url=audio_base_url,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            last_err = exc
            if attempt < attempts:
                wait_sec = 3 * attempt
                print(
                    f"  Release upload retry {attempt}/{attempts - 1} for {mp3_path.name} "
                    f"in {wait_sec}s ({exc})..."
                )
                time.sleep(wait_sec)
    raise RuntimeError(f"gh release upload failed for {mp3_path.name}: {last_err}") from last_err


def select_pending_posts(
    all_posts: list[dict[str, Any]],
    episodes: dict[str, dict[str, Any]],
    ignored_slugs: set[str],
    order: str = "oldest",
    upgrade_outdated: bool = False,
    shard_index: int | None = None,
    shard_count: int | None = None,
) -> list[dict[str, Any]]:
    """Select and deterministically shard posts needing synthesis or quality upgrades."""
    if (shard_index is None) != (shard_count is None):
        raise ValueError("shard_index and shard_count must both be set or both be None.")
    if shard_count is not None:
        if shard_count < 1 or shard_index is None or not (0 <= shard_index < shard_count):
            raise ValueError(f"Invalid shard coordinates: index={shard_index}, count={shard_count}")

    pending: list[dict[str, Any]] = []
    for post in all_posts:
        slug = post.get("slug")
        if not slug or slug in ignored_slugs:
            continue
        existing = episodes.get(slug)
        if existing is None:
            pending.append(post)
        elif upgrade_outdated and int(existing.get("pipeline_version", 1)) < PIPELINE_VERSION:
            pending.append(post)

    pending.sort(
        key=lambda p: p.get("post_date", ""),
        reverse=(order == "newest"),
    )
    if shard_count is not None and shard_index is not None:
        return [p for idx, p in enumerate(pending) if idx % shard_count == shard_index]
    return pending


def merge_shard_outputs(
    shards_dir: Path,
    state_file: Path,
    artwork_dir: Path,
) -> tuple[dict[str, Any], int]:
    """Merge sharded episodes.json files and artwork into the canonical repository state."""
    state = load_json(state_file) if state_file.exists() else {"episodes": {}}
    episodes: dict[str, dict[str, Any]] = state.setdefault("episodes", {})

    merged_slugs: set[str] = set()
    for shard_json in sorted(shards_dir.rglob("episodes.json")):
        shard_data = load_json(shard_json)
        shard_eps = shard_data.get("episodes", {})
        if not isinstance(shard_eps, dict):
            continue
        for slug, ep in shard_eps.items():
            if not isinstance(ep, dict):
                continue
            cur = episodes.get(slug)
            cur_ver = int(cur.get("pipeline_version", 1)) if cur else -1
            new_ver = int(ep.get("pipeline_version", 1))
            cur_ts = cur.get("generated_at", "") if cur else ""
            new_ts = ep.get("generated_at", "")
            if cur is None or new_ver > cur_ver or (new_ver == cur_ver and new_ts >= cur_ts):
                episodes[slug] = ep
                merged_slugs.add(slug)

    artwork_dir.mkdir(parents=True, exist_ok=True)
    for jpg in sorted(shards_dir.rglob("artwork/*.jpg")):
        dest = artwork_dir / jpg.name
        if jpg.name == "show-cover.jpg" and dest.exists():
            continue
        if jpg.resolve() != dest.resolve():
            shutil.copy2(jpg, dest)

    save_json(state_file, state)
    return state, len(merged_slugs)


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
        help="Max new episodes to synthesize per run (default: 5).",
    )
    parser.add_argument(
        "--order",
        choices=["oldest", "newest"],
        default="oldest",
        help="Order to process pending episodes (default: oldest).",
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
    mode_group.add_argument(
        "--export-backfill",
        action="store_true",
        help="Export all historical Substack posts into state/backfill_queue.json.",
    )
    mode_group.add_argument(
        "--merge-shards-dir",
        type=Path,
        default=None,
        help="Merge shard episodes.json/artwork under this directory and rebuild RSS/HTML.",
    )
    parser.add_argument(
        "--upgrade-outdated",
        action="store_true",
        help="Also reprocess episodes generated with an older pipeline_version.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=None,
        help="Zero-based worker shard index for parallel processing.",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=None,
        help="Total number of parallel worker shards.",
    )
    parser.add_argument(
        "--state-out",
        type=Path,
        default=None,
        help="Write only episodes built in this run to this state file and skip RSS/HTML rebuild.",
    )
    parser.add_argument(
        "--artwork-out-dir",
        type=Path,
        default=None,
        help="Write episode artwork JPEGs to this directory instead of docs/artwork/.",
    )
    args = parser.parse_args()

    if (args.shard_index is None) != (args.shard_count is None):
        raise ValueError("--shard-index and --shard-count must be passed together.")
    if args.shard_count is not None and (
        args.shard_count < 1 or args.shard_index is None or not (0 <= args.shard_index < args.shard_count)
    ):
        raise ValueError(f"Invalid shard arguments: index={args.shard_index}, count={args.shard_count}")

    settings = load_json(CONFIG_DIR / "settings.json")
    if args.export_backfill:
        count = export_full_archive_to_backfill(settings["substack_subdomain"], BACKFILL_QUEUE_PATH)
        print(f"Exported {count} historical posts -> {BACKFILL_QUEUE_PATH}")
        return 0

    pronunciations = load_json(CONFIG_DIR / "pronunciations.json").get("replacements", {})
    ignored_slugs = load_ignored_slugs(IGNORE_PATH)
    owner, repo = resolve_github_coords(settings)
    base_pages_url = f"https://{owner}.github.io/{repo}"

    if args.local_only:
        preview_dir = BUILD_DIR / "preview"
        audio_dir = preview_dir / "audio"
        artwork_dir = args.artwork_out_dir or (preview_dir / "artwork")
        state_file = BUILD_DIR / "local_episodes.json"
        out_xml = preview_dir / "podcast.xml"
        out_html = preview_dir / "index.html"
        base_pages_url = preview_dir.resolve().as_uri()
    else:
        audio_dir = BUILD_DIR / "audio"
        artwork_dir = args.artwork_out_dir or (DOCS_DIR / "artwork")
        state_file = STATE_PATH
        out_xml = DOCS_DIR / "podcast.xml"
        out_html = DOCS_DIR / "index.html"

    state = load_json(state_file) if state_file.exists() else {"episodes": {}}
    baseline_episodes: dict[str, dict[str, Any]] = state.setdefault("episodes", {})

    if args.merge_shards_dir is not None:
        state, merged_count = merge_shard_outputs(
            shards_dir=args.merge_shards_dir,
            state_file=state_file,
            artwork_dir=artwork_dir,
        )
        print(f"Merged {merged_count} shard episode(s) from {args.merge_shards_dir} -> {state_file}.")
        baseline_episodes = state.setdefault("episodes", {})

    show_cover_path = artwork_dir / "show-cover.jpg"
    repo_show_cover = DOCS_DIR / "artwork" / "show-cover.jpg"
    if not show_cover_path.exists():
        if repo_show_cover.exists() and repo_show_cover.resolve() != show_cover_path.resolve():
            show_cover_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_show_cover, show_cover_path)
        else:
            print("Preparing 1400x1400 show cover artwork...")
            prepare_square_artwork(settings["show_logo_source_url"], show_cover_path)

    failed_slugs: list[str] = []
    if not args.rebuild_only and args.merge_shards_dir is None:
        if args.publish_releases and (not owner or owner == "REPLACE_WITH_GITHUB_USERNAME"):
            raise RuntimeError(
                "github_owner is still REPLACE_WITH_GITHUB_USERNAME in config/settings.json "
                "and GITHUB_REPOSITORY is not set."
            )

        out_state_file = args.state_out or state_file
        if args.state_out is not None:
            shard_state: dict[str, Any] = {"episodes": {}}
            target_episodes = shard_state["episodes"]
            save_json(out_state_file, shard_state)
        else:
            shard_state = state
            target_episodes = baseline_episodes

        print(f"Fetching newsletter RSS feed for {settings['substack_subdomain']}.substack.com...")
        all_posts = collect_all_available_posts(settings["substack_subdomain"])
        pending = select_pending_posts(
            all_posts=all_posts,
            episodes=baseline_episodes,
            ignored_slugs=ignored_slugs,
            order=args.order,
            upgrade_outdated=args.upgrade_outdated,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
        )
        shard_desc = (
            f", shard={args.shard_index}/{args.shard_count}"
            if args.shard_count is not None
            else ""
        )
        print(
            f"Found {len(all_posts)} written posts total; "
            f"{len(pending)} pending synthesis (order={args.order}, limit={args.limit}"
            f", upgrade_outdated={args.upgrade_outdated}{shard_desc})."
        )

        to_process = pending[: max(0, args.limit)]
        for idx, post in enumerate(to_process, 1):
            slug = post["slug"]
            post_url = post.get("post_url") or f"https://{settings['substack_subdomain']}.substack.com/p/{slug}"
            print(f"[{idx}/{len(to_process)}] Processing {slug}...")
            mp3_path = audio_dir / f"{slug}.mp3"

            try:
                title = clean_post_title(post.get("title") or slug)
                subtitle = (post.get("subtitle") or "").strip()
                pub_date = post.get("post_date") or ""
                year = pub_date[:4] if len(pub_date) >= 4 else ""
                raw_html = post.get("body_html") or ""
                cover_url = post.get("cover_image") or ""

                cleaned_soup = clean_substack_html(raw_html)

                ep_art_path = artwork_dir / f"{slug}.jpg"
                has_ep_art = False
                if cover_url:
                    try:
                        has_ep_art = prepare_square_artwork(cover_url, ep_art_path)
                    except Exception as exc:
                        print(f"  Warning: could not process cover image for {slug} ({exc}); using show cover.")
                if not has_ep_art:
                    shutil.copy2(show_cover_path, ep_art_path)

                ep_art_url = f"artwork/{slug}.jpg" if args.local_only else f"{base_pages_url}/artwork/{slug}.jpg"

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
                        mp3_path,
                        settings["release_tag"],
                        owner,
                        repo,
                        audio_base_url=settings.get("audio_base_url", ""),
                    )
                    mp3_path.unlink(missing_ok=True)
                else:
                    audio_url = mp3_path.resolve().as_uri()

                target_episodes[slug] = {
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
                    "pipeline_version": PIPELINE_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                save_json(out_state_file, shard_state)
                time.sleep(0.25)
            except Exception as exc:
                mp3_path.unlink(missing_ok=True)
                failed_slugs.append(slug)
                print(f"  ERROR processing {slug}: {exc}", file=sys.stderr)

    if args.state_out is not None and not args.rebuild_only and args.merge_shards_dir is None:
        print(
            f"Saved shard output ({len(target_episodes)} episodes) -> {out_state_file} "
            "(skipped RSS/HTML rebuild)."
        )
    else:
        rss_count = build_podcast_rss(
            settings=settings,
            episodes=baseline_episodes,
            ignored_slugs=ignored_slugs,
            base_pages_url=base_pages_url,
            output_xml_path=out_xml,
            show_cover_href="artwork/show-cover.jpg" if args.local_only else None,
            feed_self_href="podcast.xml" if args.local_only else None,
        )
        html_count = build_web_player_html(
            settings=settings,
            episodes=baseline_episodes,
            ignored_slugs=ignored_slugs,
            output_html_path=out_html,
            local_preview=args.local_only,
        )
        print(f"Built {out_xml} ({rss_count} episodes) and {out_html} ({html_count} episodes).")
    if failed_slugs:
        print(f"FAILED_EPISODES: {', '.join(failed_slugs)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
