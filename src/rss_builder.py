"""Build valid Podcast RSS 2.0 XML and a clean HTML episode player page."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
import re
from typing import Any, Mapping
from xml.sax.saxutils import escape as xml_escape


def _parse_iso_dt(value: str) -> datetime:
    cleaned = (value or "").strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.now(timezone.utc)


def _format_duration_hms(total_seconds: int) -> str:
    sec = max(1, int(total_seconds))
    hours, rem = divmod(sec, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _cdata(html_text: str) -> str:
    safe = (html_text or "").replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{safe}]]>"


def _active_sorted_episodes(
    episodes: Mapping[str, Mapping[str, Any]],
    ignored_slugs: set[str],
) -> list[Mapping[str, Any]]:
    active = [
        ep
        for slug, ep in episodes.items()
        if slug not in ignored_slugs and ep.get("audio_url")
    ]
    active.sort(key=lambda ep: ep.get("pub_date", ""), reverse=True)
    return active


def build_podcast_rss(
    settings: Mapping[str, Any],
    episodes: Mapping[str, Mapping[str, Any]],
    ignored_slugs: set[str],
    base_pages_url: str,
    output_xml_path: Path,
    show_cover_href: str | None = None,
    feed_self_href: str | None = None,
) -> int:
    """Write a Podcast RSS 2.0 XML feed excluding ignored slugs. Returns episode count."""
    output_xml_path.parent.mkdir(parents=True, exist_ok=True)
    base = base_pages_url.rstrip("/")
    cover_url = show_cover_href or f"{base}/artwork/show-cover.jpg"
    self_url = feed_self_href or f"{base}/podcast.xml"

    active = _active_sorted_episodes(episodes, ignored_slugs)
    now_rfc = format_datetime(datetime.now(timezone.utc))

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"',
        '     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"',
        '     xmlns:content="http://purl.org/rss/1.0/modules/content/"',
        '     xmlns:atom="http://www.w3.org/2005/Atom"',
        '     xmlns:podcast="https://podcastindex.org/namespace/1.0">',
        "  <channel>",
        f"    <title>{xml_escape(settings['show_title'])}</title>",
        f"    <link>{xml_escape(settings['substack_url'])}</link>",
        "    <language>en-us</language>",
        f"    <description>{xml_escape(settings['show_description'])}</description>",
        f"    <lastBuildDate>{now_rfc}</lastBuildDate>",
        f'    <atom:link href="{xml_escape(self_url)}" rel="self" type="application/rss+xml"/>',
        f"    <itunes:subtitle>{xml_escape(settings['show_subtitle'])}</itunes:subtitle>",
        f"    <itunes:author>{xml_escape(settings['author'])}</itunes:author>",
        f"    <itunes:summary>{xml_escape(settings['show_description'])}</itunes:summary>",
        "    <itunes:type>episodic</itunes:type>",
        "    <itunes:owner>",
        f"      <itunes:name>{xml_escape(settings['owner_name'])}</itunes:name>",
        f"      <itunes:email>{xml_escape(settings['owner_email'])}</itunes:email>",
        "    </itunes:owner>",
        '    <itunes:category text="Religion &amp; Spirituality"/>',
        "    <itunes:explicit>false</itunes:explicit>",
        f'    <itunes:image href="{xml_escape(cover_url)}"/>',
        "    <image>",
        f"      <url>{xml_escape(cover_url)}</url>",
        f"      <title>{xml_escape(settings['show_title'])}</title>",
        f"      <link>{xml_escape(settings['substack_url'])}</link>",
        "    </image>",
    ]

    for ep in active:
        slug = ep["slug"]
        title = ep["title"]
        post_url = ep["post_url"]
        pub_rfc = format_datetime(_parse_iso_dt(ep["pub_date"]))
        summary = ep.get("summary") or title
        content_html = ep.get("content_html") or f"<p>{escape(summary)}</p>"
        audio_url = ep["audio_url"]
        audio_bytes = int(ep.get("audio_bytes") or 0)
        duration_hms = _format_duration_hms(int(ep.get("duration_sec") or 1))
        artwork_url = ep.get("artwork_url") or cover_url

        lines.extend(
            [
                "    <item>",
                f"      <title>{xml_escape(title)}</title>",
                f"      <link>{xml_escape(post_url)}</link>",
                f'      <guid isPermaLink="false">contendersvoice-{xml_escape(slug)}</guid>',
                f"      <pubDate>{pub_rfc}</pubDate>",
                f"      <description>{xml_escape(summary)}</description>",
                f"      <content:encoded>{_cdata(content_html)}</content:encoded>",
                f'      <enclosure url="{xml_escape(audio_url)}" length="{audio_bytes}" type="audio/mpeg"/>',
                f"      <itunes:author>{xml_escape(settings['author'])}</itunes:author>",
                f"      <itunes:duration>{duration_hms}</itunes:duration>",
                f'      <itunes:image href="{xml_escape(artwork_url)}"/>',
                "      <itunes:explicit>false</itunes:explicit>",
                "    </item>",
            ]
        )

    lines.extend(["  </channel>", "</rss>", ""])
    output_xml_path.write_text("\n".join(lines), encoding="utf-8")
    return len(active)


def build_web_player_html(
    settings: Mapping[str, Any],
    episodes: Mapping[str, Mapping[str, Any]],
    ignored_slugs: set[str],
    output_html_path: Path,
    local_preview: bool = False,
) -> int:
    """Write a responsive HTML podcast player page listing all active episodes."""
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    active = _active_sorted_episodes(episodes, ignored_slugs)

    cards_html: list[str] = []
    for ep in active:
        dt = _parse_iso_dt(ep["pub_date"])
        date_label = dt.strftime("%b %d, %Y")
        dur_label = _format_duration_hms(int(ep.get("duration_sec") or 1))
        size_mb = (int(ep.get("audio_bytes") or 0)) / (1024 * 1024)
        title_esc = escape(ep["title"])
        summary_esc = escape(ep.get("summary") or "")
        post_url_esc = escape(ep["post_url"], quote=True)
        audio_src = escape(
            ep.get("local_audio_rel") if local_preview and ep.get("local_audio_rel") else ep["audio_url"],
            quote=True,
        )
        art_src = escape(
            ep.get("local_artwork_rel")
            if local_preview and ep.get("local_artwork_rel")
            else ep.get("artwork_url", "artwork/show-cover.jpg"),
            quote=True,
        )
        body_html = ep.get("content_html") or f"<p>{summary_esc}</p>"
        # When previewing locally, swap remote artwork src inside body if needed? Keep body clean as rendered.
        cards_html.append(
            f"""
      <article class="episode">
        <div class="ep-top">
          <img class="ep-art" src="{art_src}" alt="{title_esc}" loading="lazy">
          <div class="ep-info">
            <div class="ep-meta">{escape(date_label)} &middot; {escape(dur_label)} &middot; {size_mb:.1f} MB</div>
            <h2>{title_esc}</h2>
            <p class="ep-summary">{summary_esc}</p>
          </div>
        </div>
        <audio controls preload="metadata" src="{audio_src}"></audio>
        <div class="ep-links">
          <a href="{post_url_esc}" target="_blank" rel="noopener">Read original on Substack &rarr;</a>
        </div>
        <details class="ep-body">
          <summary>Read full formatted article text</summary>
          <div class="ep-article">{body_html}</div>
        </details>
      </article>"""
        )

    show_title_esc = escape(settings["show_title"])
    show_desc_esc = escape(settings["show_description"])
    substack_esc = escape(settings["substack_url"], quote=True)
    website_esc = escape(settings["website_url"], quote=True)
    rss_href = "podcast.xml"
    mode_badge = (
        "Local Preview (2 Test Episodes)"
        if local_preview
        else f"{len(active)} Audio Episodes"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{show_title_esc} — Audio Podcast</title>
  <style>
    :root {{
      --bg: #f8f6f2;
      --card: #ffffff;
      --ink: #1f2421;
      --muted: #5a625d;
      --accent: #c9561e;
      --border: #e4dfd5;
      --pill: #f3ece4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 2rem 1.25rem 4rem;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.6;
    }}
    main {{ max-width: 860px; margin: 0 auto; }}
    header {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.5rem;
      margin-bottom: 1.75rem;
      display: flex;
      gap: 1.25rem;
      align-items: center;
      flex-wrap: wrap;
    }}
    .show-art {{
      width: 96px;
      height: 96px;
      border-radius: 12px;
      object-fit: cover;
      border: 1px solid var(--border);
      flex-shrink: 0;
    }}
    .eyebrow {{
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent);
      margin-bottom: 0.2rem;
    }}
    h1 {{ margin: 0 0 0.35rem; font-size: 1.7rem; line-height: 1.2; }}
    .desc {{ margin: 0 0 0.7rem; color: var(--muted); font-size: 0.95rem; }}
    .nav-links {{ display: flex; gap: 0.75rem; flex-wrap: wrap; font-size: 0.88rem; }}
    .nav-links a, .badge {{
      display: inline-block;
      padding: 0.25rem 0.65rem;
      border-radius: 999px;
      text-decoration: none;
      background: var(--pill);
      color: #6b3416;
      font-weight: 600;
    }}
    .nav-links a:hover {{ filter: brightness(0.95); }}
    .episodes {{ display: grid; gap: 1.25rem; }}
    .episode {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.35rem;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
    }}
    .ep-top {{ display: flex; gap: 1.1rem; align-items: flex-start; margin-bottom: 0.9rem; }}
    .ep-art {{
      width: 96px;
      height: 96px;
      border-radius: 10px;
      object-fit: cover;
      flex-shrink: 0;
      border: 1px solid var(--border);
    }}
    .ep-meta {{ font-size: 0.82rem; color: var(--muted); margin-bottom: 0.2rem; }}
    .ep-info h2 {{ margin: 0 0 0.35rem; font-size: 1.15rem; line-height: 1.3; }}
    .ep-summary {{ margin: 0; font-size: 0.92rem; color: var(--muted); }}
    audio {{ width: 100%; height: 40px; margin-bottom: 0.65rem; }}
    .ep-links {{ font-size: 0.88rem; margin-bottom: 0.5rem; }}
    .ep-links a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
    .ep-links a:hover {{ text-decoration: underline; }}
    details.ep-body {{
      margin-top: 0.5rem;
      border-top: 1px solid var(--border);
      padding-top: 0.6rem;
    }}
    details.ep-body summary {{
      cursor: pointer;
      font-size: 0.88rem;
      font-weight: 600;
      color: var(--muted);
    }}
    .ep-article {{
      margin-top: 0.85rem;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 0.98rem;
      color: #2b302d;
    }}
    .ep-article img {{ max-width: 100%; height: auto; border-radius: 8px; }}
    @media (max-width: 560px) {{
      .ep-top {{ flex-direction: column; }}
      .ep-art {{ width: 100%; height: auto; aspect-ratio: 1 / 1; max-width: 240px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <img class="show-art" src="artwork/show-cover.jpg" alt="{show_title_esc}">
      <div>
        <div class="eyebrow">Audio Podcast Hub &middot; {escape(mode_badge)}</div>
        <h1>{show_title_esc}</h1>
        <p class="desc">{show_desc_esc}</p>
        <div class="nav-links">
          <a href="{rss_href}">Podcast RSS Feed</a>
          <a href="{substack_esc}" target="_blank" rel="noopener">Substack</a>
          <a href="{website_esc}" target="_blank" rel="noopener">contendersvoice.com</a>
        </div>
      </div>
    </header>
    <section class="episodes">
      {"".join(cards_html)}
    </section>
  </main>
  <script>
    const players = Array.from(document.querySelectorAll("audio"));
    players.forEach((p) => {{
      p.addEventListener("play", () => {{
        players.forEach((o) => {{ if (o !== p && !o.paused) o.pause(); }});
      }});
    }});
  </script>
</body>
</html>
"""
    output_html_path.write_text(html, encoding="utf-8")
    return len(active)
