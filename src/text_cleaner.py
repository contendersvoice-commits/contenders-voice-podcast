"""Clean Substack HTML into podcast show notes and speech-ready text chunks."""

from __future__ import annotations

from html import escape
import re
from typing import Mapping

from bs4 import BeautifulSoup, Tag

STRIP_SELECTORS = (
    "div.subscription-widget-wrap-editor",
    "div.subscription-widget",
    "div.button-wrapper",
    "form",
    "button",
    "svg",
    "script",
    "style",
    "input",
    ".image-link-expand",
    ".restack-image",
    ".view-image",
)

DECORATIVE_LINE_RE = re.compile(r"^[\s\-*_—–=·•]+$")
BOILERPLATE_TAIL_RE = re.compile(
    r"^(thanks for reading|this substack is reader-supported|subscribe now)\b",
    flags=re.I,
)
BARE_URL_RE = re.compile(r"https?://\S+")


def clean_post_title(raw_title: str) -> str:
    """Normalize Substack titles that contain embedded newlines or awkward spacing."""
    title = re.sub(r"\s*\n+\s*", " — ", raw_title or "")
    title = re.sub(r"\s{2,}", " ", title).strip()
    title = re.sub(r"\s+([?!.,;:])", r"\1", title)
    return title or "Untitled Post"


def _norm_compare(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def clean_substack_html(raw_html: str) -> BeautifulSoup:
    """Strip Substack subscribe widgets, editor controls, and clutter from article HTML."""
    soup = BeautifulSoup(raw_html or "", "html.parser")

    for selector in STRIP_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    # Remove bare subscribe / placeholder text remnants and decorative divider paragraphs
    for tag in list(soup.find_all(["p", "div", "span", "figure"])):
        if tag.name == "figure":
            img = tag.find("img")
            if img is None:
                tag.decompose()
            continue

        has_media = tag.find(["img", "iframe", "video", "audio", "hr"]) is not None
        text = tag.get_text(" ", strip=True)
        if not has_media and (
            not text
            or DECORATIVE_LINE_RE.match(text)
            or BOILERPLATE_TAIL_RE.match(text)
        ):
            tag.decompose()

    # Simplify <img> tags so RSS readers render clean images without huge data-attrs
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        alt = img.get("alt") or ""
        img.attrs = {"src": src}
        if alt:
            img["alt"] = alt

    return soup


def _first_meaningful_element_has_image(soup: BeautifulSoup) -> bool:
    for child in soup.children:
        if isinstance(child, Tag):
            text = child.get_text(" ", strip=True)
            if child.find("img") is not None or child.name == "img":
                return True
            if text:
                return False
    return False


def build_show_notes_html(
    post_title: str,
    post_url: str,
    cleaned_soup: BeautifulSoup,
    artwork_url: str,
) -> str:
    """Build clean HTML show notes with article cover image, note, and full article text."""
    escaped_title = escape(post_title)
    escaped_url = escape(post_url, quote=True)
    escaped_art = escape(artwork_url, quote=True)

    parts: list[str] = []
    if artwork_url and not _first_meaningful_element_has_image(cleaned_soup):
        parts.append(f'<p><img src="{escaped_art}" alt="{escaped_title}" /></p>')

    parts.append(
        f"<p><em>Audio edition of <a href=\"{escaped_url}\">{escaped_title}</a> on Contender's Voice. "
        f'For more, visit <a href="https://www.contendersvoice.com/">contendersvoice.com</a>.</em></p>'
    )
    parts.append(str(cleaned_soup).strip())
    return "\n".join(p for p in parts if p)


def _apply_pronunciations(text: str, pronunciations: Mapping[str, str]) -> str:
    """Apply longest-first, case-insensitive whole-word pronunciation replacements."""
    if not pronunciations:
        return text
    ordered = sorted(pronunciations.items(), key=lambda kv: len(kv[0]), reverse=True)
    for term, phonetic in ordered:
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags=re.IGNORECASE)
        text = pattern.sub(phonetic, text)
    return text


def _clean_text_for_speech(text: str, pronunciations: Mapping[str, str]) -> str:
    """Normalize punctuation, brackets, abbreviations, URLs, and Hebrew terms for TTS."""
    out = BARE_URL_RE.sub("", text)
    out = re.sub(r"\s*\[\s*([^\]]+?)\s*\]", r", meaning \1,", out)
    out = re.sub(r"\s*--\s*", " — ", out)
    out = re.sub(r"\bi\.e\.", "that is,", out, flags=re.IGNORECASE)
    out = re.sub(r"\be\.g\.", "for example,", out, flags=re.IGNORECASE)
    out = _apply_pronunciations(out, pronunciations)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\s+([,.;:?!])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def _extract_leaf_blocks(soup: BeautifulSoup) -> list[str]:
    """Extract readable text blocks in document order without duplicating nested tags."""
    blocks: list[str] = []
    block_tags = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "figcaption")
    for el in soup.find_all(block_tags):
        if el.name == "blockquote" and el.find(["p", "li"]):
            continue
        if el.name == "li" and el.find("p"):
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if not text or DECORATIVE_LINE_RE.match(text):
            continue
        blocks.append(text)
    return blocks


def _split_long_paragraph(text: str, max_chars: int) -> list[str]:
    """Split an extra-long paragraph on sentence boundaries so TTS stays reliable."""
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            if len(sentence) <= max_chars:
                current = sentence
            else:
                # Hard-wrap exceptionally long run-on sentences on commas/spaces
                words = sentence.split()
                part = ""
                for word in words:
                    if len(part) + len(word) + 1 <= max_chars:
                        part = f"{part} {word}".strip()
                    else:
                        if part:
                            chunks.append(part)
                        part = word
                current = part
    if current:
        chunks.append(current)
    return chunks


def build_spoken_chunks(
    title: str,
    subtitle: str,
    cleaned_soup: BeautifulSoup,
    pronunciations: Mapping[str, str],
    max_chars: int = 600,
) -> tuple[list[str], str]:
    """Return (intro_and_body_chunks, brief_outro_text) formatted for natural narration."""
    raw_blocks = _extract_leaf_blocks(cleaned_soup)

    norm_title = _norm_compare(title)
    norm_sub = _norm_compare(subtitle)

    paragraphs: list[str] = ["Contender's Voice, by Hutch Church.", title]
    if subtitle and norm_sub and norm_sub not in norm_title:
        first_two_norm = _norm_compare(" ".join(raw_blocks[:2]))
        if norm_sub not in first_two_norm:
            paragraphs.append(subtitle)

    for idx, block in enumerate(raw_blocks):
        norm_block = _norm_compare(block)
        if idx < 2 and norm_block and (norm_block == norm_title or norm_block == norm_sub):
            continue
        paragraphs.append(block)

    spoken_paragraphs: list[str] = []
    for para in paragraphs:
        cleaned = _clean_text_for_speech(para, pronunciations)
        if cleaned:
            spoken_paragraphs.append(cleaned)

    chunks: list[str] = []
    current = ""
    for para in spoken_paragraphs:
        for piece in _split_long_paragraph(para, max_chars):
            if not current:
                current = piece
            elif len(current) + len(piece) + 2 <= max_chars:
                current = f"{current}\n\n{piece}"
            else:
                chunks.append(current)
                current = piece
    if current:
        chunks.append(current)

    outro = _clean_text_for_speech("For more, visit contendersvoice.com.", pronunciations)
    return chunks, outro
