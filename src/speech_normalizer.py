"""Deterministic speech-shaping normalizer for neural TTS narration."""

from __future__ import annotations

import re
from typing import Mapping

NON_AUDIO_BLOCK_PATTERNS = (
    re.compile(r"^\(?\s*audio available to subscribers\s*\)?\.?$", re.IGNORECASE),
    re.compile(r"^audio\.\s*click the black triangle\b", re.IGNORECASE),
)

BARE_URL_RE = re.compile(r"https?://\S+")
MALFORMED_URL_RE = re.compile(
    r"\b[A-Za-z]?www\.(?!contendersvoice\.com\b)\S+(?:\s+\.[A-Za-z0-9/_.-]+)*",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

ORDINAL_WORDS = {"1": "First", "2": "Second", "3": "Third"}

# Canonical 66 books + Hebrew Torah book names + common abbreviations.
# Tuple format: (spoken_name, is_psalm, requires_strong_context)
_RAW_BOOK_TABLE: dict[str, tuple[str, bool, bool]] = {
    # Old Testament
    "genesis": ("Genesis", False, False),
    "gen": ("Genesis", False, False),
    "ge": ("Genesis", False, True),
    "gn": ("Genesis", False, True),
    "beresheit": ("Beresheit", False, False),
    "b’resheit": ("B’resheit", False, False),
    "b'resheit": ("B'resheit", False, False),
    "bereshit": ("Bereshit", False, False),
    "bereishit": ("Bereishit", False, False),
    "exodus": ("Exodus", False, False),
    "exod": ("Exodus", False, False),
    "exo": ("Exodus", False, False),
    "ex": ("Exodus", False, True),
    "shemot": ("Shemot", False, False),
    "sh’mot": ("Sh’mot", False, False),
    "sh'mot": ("Sh'mot", False, False),
    "leviticus": ("Leviticus", False, False),
    "levit": ("Leviticus", False, False),
    "lev": ("Leviticus", False, False),
    "lv": ("Leviticus", False, True),
    "vayikra": ("Vayikra", False, False),
    "numbers": ("Numbers", False, False),
    "numb": ("Numbers", False, False),
    "num": ("Numbers", False, False),
    "nm": ("Numbers", False, True),
    "nb": ("Numbers", False, True),
    "bamidbar": ("Bamidbar", False, False),
    "deuteronomy": ("Deuteronomy", False, False),
    "deut": ("Deuteronomy", False, False),
    "deu": ("Deuteronomy", False, False),
    "dt": ("Deuteronomy", False, True),
    "devarim": ("Devarim", False, False),
    "dvarim": ("Dvarim", False, False),
    "joshua": ("Joshua", False, False),
    "josh": ("Joshua", False, False),
    "jos": ("Joshua", False, True),
    "jsh": ("Joshua", False, True),
    "judges": ("Judges", False, False),
    "judg": ("Judges", False, False),
    "jdg": ("Judges", False, False),
    "jdgs": ("Judges", False, False),
    "ruth": ("Ruth", False, False),
    "rth": ("Ruth", False, True),
    "samuel": ("Samuel", False, False),
    "samual": ("Samuel", False, False),
    "sam": ("Samuel", False, False),
    "sm": ("Samuel", False, True),
    "sa": ("Samuel", False, True),
    "1 samuel": ("First Samuel", False, False),
    "1 sam": ("First Samuel", False, False),
    "1 sm": ("First Samuel", False, True),
    "1 sa": ("First Samuel", False, True),
    "1st samuel": ("First Samuel", False, False),
    "first samuel": ("First Samuel", False, False),
    "i samuel": ("First Samuel", False, False),
    "i sam": ("First Samuel", False, False),
    "2 samuel": ("Second Samuel", False, False),
    "2 sam": ("Second Samuel", False, False),
    "2 sm": ("Second Samuel", False, True),
    "2 sa": ("Second Samuel", False, True),
    "2nd samuel": ("Second Samuel", False, False),
    "second samuel": ("Second Samuel", False, False),
    "ii samuel": ("Second Samuel", False, False),
    "ii sam": ("Second Samuel", False, False),
    "1 kings": ("First Kings", False, False),
    "1 kgs": ("First Kings", False, False),
    "1 ki": ("First Kings", False, False),
    "1st kings": ("First Kings", False, False),
    "first kings": ("First Kings", False, False),
    "i kings": ("First Kings", False, False),
    "i kgs": ("First Kings", False, False),
    "2 kings": ("Second Kings", False, False),
    "2 kgs": ("Second Kings", False, False),
    "2 ki": ("Second Kings", False, False),
    "2nd kings": ("Second Kings", False, False),
    "second kings": ("Second Kings", False, False),
    "ii kings": ("Second Kings", False, False),
    "ii kgs": ("Second Kings", False, False),
    "1 chronicles": ("First Chronicles", False, False),
    "1 chron": ("First Chronicles", False, False),
    "1 chr": ("First Chronicles", False, False),
    "1 ch": ("First Chronicles", False, True),
    "1st chronicles": ("First Chronicles", False, False),
    "first chronicles": ("First Chronicles", False, False),
    "i chronicles": ("First Chronicles", False, False),
    "i chron": ("First Chronicles", False, False),
    "2 chronicles": ("Second Chronicles", False, False),
    "2 chron": ("Second Chronicles", False, False),
    "2 chr": ("Second Chronicles", False, False),
    "2 ch": ("Second Chronicles", False, True),
    "2nd chronicles": ("Second Chronicles", False, False),
    "second chronicles": ("Second Chronicles", False, False),
    "ii chronicles": ("Second Chronicles", False, False),
    "ii chron": ("Second Chronicles", False, False),
    "ezra": ("Ezra", False, False),
    "ezr": ("Ezra", False, False),
    "nehemiah": ("Nehemiah", False, False),
    "neh": ("Nehemiah", False, False),
    "ne": ("Nehemiah", False, True),
    "esther": ("Esther", False, False),
    "esth": ("Esther", False, False),
    "est": ("Esther", False, True),
    "es": ("Esther", False, True),
    "job": ("Job", False, False),
    "jb": ("Job", False, True),
    "psalms": ("Psalms", True, False),
    "psalm": ("Psalm", True, False),
    "psa": ("Psalm", True, False),
    "pss": ("Psalms", True, False),
    "ps": ("Psalm", True, True),
    "proverbs": ("Proverbs", False, False),
    "prov": ("Proverbs", False, False),
    "pro": ("Proverbs", False, True),
    "prv": ("Proverbs", False, False),
    "pr": ("Proverbs", False, True),
    "ecclesiastes": ("Ecclesiastes", False, False),
    "eccles": ("Ecclesiastes", False, False),
    "eccl": ("Ecclesiastes", False, False),
    "ecc": ("Ecclesiastes", False, False),
    "ec": ("Ecclesiastes", False, True),
    "song of solomon": ("Song of Solomon", False, False),
    "song of songs": ("Song of Songs", False, False),
    "song": ("Song of Solomon", False, True),
    "sos": ("Song of Solomon", False, True),
    "cant": ("Song of Solomon", False, True),
    "canticles": ("Song of Solomon", False, False),
    "isaiah": ("Isaiah", False, False),
    "isa": ("Isaiah", False, False),
    "is": ("Isaiah", False, True),
    "jeremiah": ("Jeremiah", False, False),
    "jer": ("Jeremiah", False, False),
    "je": ("Jeremiah", False, True),
    "jr": ("Jeremiah", False, True),
    "lamentations": ("Lamentations", False, False),
    "lam": ("Lamentations", False, False),
    "la": ("Lamentations", False, True),
    "ezekiel": ("Ezekiel", False, False),
    "ezek": ("Ezekiel", False, False),
    "eze": ("Ezekiel", False, False),
    "ezk": ("Ezekiel", False, False),
    "ez": ("Ezekiel", False, True),
    "daniel": ("Daniel", False, False),
    "dan": ("Daniel", False, False),
    "da": ("Daniel", False, True),
    "dn": ("Daniel", False, True),
    "hosea": ("Hosea", False, False),
    "hos": ("Hosea", False, False),
    "ho": ("Hosea", False, True),
    "joel": ("Joel", False, False),
    "jl": ("Joel", False, True),
    "amos": ("Amos", False, False),
    "am": ("Amos", False, True),
    "obadiah": ("Obadiah", False, False),
    "obad": ("Obadiah", False, False),
    "ob": ("Obadiah", False, True),
    "jonah": ("Jonah", False, False),
    "jon": ("Jonah", False, True),
    "jnh": ("Jonah", False, False),
    "micah": ("Micah", False, False),
    "mic": ("Micah", False, False),
    "mc": ("Micah", False, True),
    "nahum": ("Nahum", False, False),
    "nah": ("Nahum", False, False),
    "na": ("Nahum", False, True),
    "habakkuk": ("Habakkuk", False, False),
    "hab": ("Habakkuk", False, False),
    "hb": ("Habakkuk", False, True),
    "zephaniah": ("Zephaniah", False, False),
    "zeph": ("Zephaniah", False, False),
    "zep": ("Zephaniah", False, False),
    "zp": ("Zephaniah", False, True),
    "haggai": ("Haggai", False, False),
    "hag": ("Haggai", False, False),
    "hg": ("Haggai", False, True),
    "zechariah": ("Zechariah", False, False),
    "zech": ("Zechariah", False, False),
    "zec": ("Zechariah", False, False),
    "zc": ("Zechariah", False, True),
    "malachi": ("Malachi", False, False),
    "mal": ("Malachi", False, False),
    "ml": ("Malachi", False, True),
    # New Testament
    "matthew": ("Matthew", False, False),
    "matt": ("Matthew", False, False),
    "mat": ("Matthew", False, True),
    "mt": ("Matthew", False, True),
    "mark": ("Mark", False, False),
    "mrk": ("Mark", False, False),
    "mk": ("Mark", False, True),
    "mr": ("Mark", False, True),
    "luke": ("Luke", False, False),
    "luk": ("Luke", False, False),
    "lk": ("Luke", False, True),
    "john": ("John", False, False),
    "jhn": ("John", False, False),
    "jn": ("John", False, True),
    "acts": ("Acts", False, False),
    "act": ("Acts", False, True),
    "ac": ("Acts", False, True),
    "romans": ("Romans", False, False),
    "rom": ("Romans", False, False),
    "ro": ("Romans", False, True),
    "rm": ("Romans", False, True),
    "1 corinthians": ("First Corinthians", False, False),
    "1 cor": ("First Corinthians", False, False),
    "1 co": ("First Corinthians", False, True),
    "1st corinthians": ("First Corinthians", False, False),
    "first corinthians": ("First Corinthians", False, False),
    "i corinthians": ("First Corinthians", False, False),
    "i cor": ("First Corinthians", False, False),
    "2 corinthians": ("Second Corinthians", False, False),
    "2 cor": ("Second Corinthians", False, False),
    "2 co": ("Second Corinthians", False, True),
    "2nd corinthians": ("Second Corinthians", False, False),
    "second corinthians": ("Second Corinthians", False, False),
    "ii corinthians": ("Second Corinthians", False, False),
    "ii cor": ("Second Corinthians", False, False),
    "galatians": ("Galatians", False, False),
    "galatianss": ("Galatians", False, False),
    "gal": ("Galatians", False, False),
    "ga": ("Galatians", False, True),
    "ephesians": ("Ephesians", False, False),
    "ephes": ("Ephesians", False, False),
    "eph": ("Ephesians", False, False),
    "philippians": ("Philippians", False, False),
    "phil": ("Philippians", False, False),
    "php": ("Philippians", False, False),
    "colossians": ("Colossians", False, False),
    "col": ("Colossians", False, False),
    "1 thessalonians": ("First Thessalonians", False, False),
    "1 thess": ("First Thessalonians", False, False),
    "1 thes": ("First Thessalonians", False, False),
    "1 th": ("First Thessalonians", False, True),
    "1st thessalonians": ("First Thessalonians", False, False),
    "first thessalonians": ("First Thessalonians", False, False),
    "i thessalonians": ("First Thessalonians", False, False),
    "i thess": ("First Thessalonians", False, False),
    "2 thessalonians": ("Second Thessalonians", False, False),
    "2 thess": ("Second Thessalonians", False, False),
    "2 thes": ("Second Thessalonians", False, False),
    "2 th": ("Second Thessalonians", False, True),
    "2nd thessalonians": ("Second Thessalonians", False, False),
    "second thessalonians": ("Second Thessalonians", False, False),
    "ii thessalonians": ("Second Thessalonians", False, False),
    "ii thess": ("Second Thessalonians", False, False),
    "1 timothy": ("First Timothy", False, False),
    "1 tim": ("First Timothy", False, False),
    "1 ti": ("First Timothy", False, True),
    "1st timothy": ("First Timothy", False, False),
    "first timothy": ("First Timothy", False, False),
    "i timothy": ("First Timothy", False, False),
    "i tim": ("First Timothy", False, False),
    "2 timothy": ("Second Timothy", False, False),
    "2 tim": ("Second Timothy", False, False),
    "2 ti": ("Second Timothy", False, True),
    "2nd timothy": ("Second Timothy", False, False),
    "second timothy": ("Second Timothy", False, False),
    "ii timothy": ("Second Timothy", False, False),
    "ii tim": ("Second Timothy", False, False),
    "titus": ("Titus", False, False),
    "tit": ("Titus", False, True),
    "philemon": ("Philemon", False, False),
    "philem": ("Philemon", False, False),
    "phlm": ("Philemon", False, False),
    "phm": ("Philemon", False, True),
    "hebrews": ("Hebrews", False, False),
    "heb": ("Hebrews", False, False),
    "james": ("James", False, False),
    "jas": ("James", False, False),
    "jm": ("James", False, True),
    "1 peter": ("First Peter", False, False),
    "1 pet": ("First Peter", False, False),
    "1 pe": ("First Peter", False, True),
    "1 pt": ("First Peter", False, True),
    "1st peter": ("First Peter", False, False),
    "first peter": ("First Peter", False, False),
    "i peter": ("First Peter", False, False),
    "i pet": ("First Peter", False, False),
    "2 peter": ("Second Peter", False, False),
    "2 pet": ("Second Peter", False, False),
    "2 pe": ("Second Peter", False, True),
    "2 pt": ("Second Peter", False, True),
    "2nd peter": ("Second Peter", False, False),
    "second peter": ("Second Peter", False, False),
    "ii peter": ("Second Peter", False, False),
    "ii pet": ("Second Peter", False, False),
    "1 john": ("First John", False, False),
    "1 jhn": ("First John", False, False),
    "1 jn": ("First John", False, True),
    "1st john": ("First John", False, False),
    "first john": ("First John", False, False),
    "i john": ("First John", False, False),
    "2 john": ("Second John", False, False),
    "2 jhn": ("Second John", False, False),
    "2 jn": ("Second John", False, True),
    "2nd john": ("Second John", False, False),
    "second john": ("Second John", False, False),
    "ii john": ("Second John", False, False),
    "3 john": ("Third John", False, False),
    "3 jhn": ("Third John", False, False),
    "3 jn": ("Third John", False, True),
    "3rd john": ("Third John", False, False),
    "third john": ("Third John", False, False),
    "iii john": ("Third John", False, False),
    "jude": ("Jude", False, False),
    "jud": ("Jude", False, True),
    "revelation": ("Revelation", False, False),
    "rev": ("Revelation", False, False),
    "re": ("Revelation", False, True),
}

# Buildlongest-first alternation for Bible book detection in citations.
# Each key may have optional spaces collapsed as \s+ so multi-word names match flexibly.
_SORTED_BOOK_KEYS = sorted(_RAW_BOOK_TABLE.keys(), key=len, reverse=True)
_BOOK_ALT = "|".join(re.escape(k).replace(r"\ ", r"\s+") for k in _SORTED_BOOK_KEYS)
# Require start at word boundary (or digit+letter boundary not needed before book),
# optional trailing period or typo comma (`Gen, 31:3`), followed cleanly by digit lookahead.
BOOK_CITE_START_RE = re.compile(
    rf"(?<![A-Za-z0-9])({_BOOK_ALT})(?:\s*([.,]))?\s*(?=\d)",
    re.IGNORECASE,
)

# Standalone numbered book names (even without chapter/verse numbers)
_NUMBERED_BASE_BOOKS: dict[str, str] = {
    "samuel": "Samuel",
    "samual": "Samuel",
    "sam": "Samuel",
    "kings": "Kings",
    "kgs": "Kings",
    "ki": "Kings",
    "chronicles": "Chronicles",
    "chron": "Chronicles",
    "chr": "Chronicles",
    "corinthians": "Corinthians",
    "cor": "Corinthians",
    "thessalonians": "Thessalonians",
    "thess": "Thessalonians",
    "thes": "Thessalonians",
    "timothy": "Timothy",
    "tim": "Timothy",
    "peter": "Peter",
    "pet": "Peter",
    "john": "John",
    "jhn": "John",
    "jn": "John",
}
_NUMBERED_BASE_ALT = "|".join(sorted(_NUMBERED_BASE_BOOKS.keys(), key=len, reverse=True))
STANDALONE_NUMBERED_BOOK_RE = re.compile(
    rf"(?<![.\d])\b([123])\s+({_NUMBERED_BASE_ALT})\.?\b",
    re.IGNORECASE,
)
# Lookahead guard so citation chains don't swallow `1` / `2` / `3` belonging to the next book!
NUMBERED_BOOK_LOOKAHEAD_RE = re.compile(
    rf"^\s*([123])\s+(?:{_NUMBERED_BASE_ALT})\b",
    re.IGNORECASE,
)

# Bracket pre-context & inner-content cues for natural phrasing
_GLUE_PRECEDING_WORDS = {
    "a", "an", "the", "of", "in", "to", "for", "with", "on", "at", "by", "from",
    "into", "through", "unto", "toward", "her", "his", "their", "our", "my", "your",
    "its", "and", "or", "nor",
}
_GLUE_INNER_WORDS = {
    "of", "an", "a", "the", "and", "or", "so does", "truly", "faith in",
    "goat", "young", "they", "it", "them",
}
_PREP_PREFIX_RE = re.compile(
    r"^(?:to|for|in|of|with|on|at|from|by|into|upon|as|or|and)\s+\S+",
    re.IGNORECASE,
)

US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
_STATE_ALT = "|".join(US_STATES.keys())
STATE_AFTER_CITY_RE = re.compile(
    rf"(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}},\s+)({_STATE_ALT})(?=\s*(?:[.,;:!?)]|\bin\s+\d{{4}}\b|\band\b|$))"
)

ALL_CAPS_EMPHASIS_WORDS = {
    "NEW", "YOU", "YES", "NO", "ALL", "WHY", "PRAY", "WE", "WAY", "NEXT", "LIKE",
    "CONTEND", "NOT", "NOW", "MUST", "NEVER", "ALWAYS", "EVERY", "TRUTH", "WORD",
    "GOD", "FAITH", "LOVE", "LAW", "GRACE", "OBEY", "LIVE", "READ", "NOTE", "POINT",
    "LEARN", "STOP", "WAIT", "LOOK", "HEAR", "LISTEN", "BEWARE", "WARNING",
    "IMPORTANT", "REMEMBER", "AUDIO", "WHOSE", "PATH", "ARE", "ON",
}
_KEEP_UPPER_IN_PHRASE = {"US", "USA", "UN", "AI", "DNA", "LSD", "KJV", "ESV", "NASB", "NIV", "GNT"}


def is_non_audio_block(text: str) -> bool:
    """Return True if a text block is a web-UI prompt not meant for podcast listeners."""
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    return any(pat.match(cleaned) for pat in NON_AUDIO_BLOCK_PATTERNS)


def _strip_urls_and_meta(text: str) -> str:
    """Remove raw URLs, copy-paste artifacts, and visual-only bracket attributions."""
    out = BARE_URL_RE.sub("", text)
    out = MALFORMED_URL_RE.sub("", out)
    out = EMAIL_RE.sub(r"\1 at \2", out)
    out = re.sub(r"(?i)\b(?:Pgs?\.\s*){2,}", "Pages ", out)
    # Remove parenthetical/standalone visual bracket notes invisible to audio listeners
    out = re.sub(
        r"(?i)\s*;?\s*brackets?\s+(?:(?:added|inserted)\s+)?(?:by\s+)?C\.?V\.?\s*",
        " ",
        out,
    )
    out = re.sub(
        r"(?i)\bbrackets?\s*(?:[-–—]\s*|added\s+|inserted\s+)?(?:by\s+)?C\.?V\.?\s*(?:inserts?)?\s*\.?",
        "",
        out,
    )
    return out


def _normalize_typography(text: str) -> str:
    """Normalize arrows, dashes, spacing typos, symbols, and stacked punctuation."""
    out = re.sub(r"\bI\s+f\b", "If", text)
    out = re.sub(r"\bfInd\b", "find", out)
    out = re.sub(r"(?:(?<=^)|(?<=\s))(\d+)\.([A-Za-z])", r"\1. \2", out)
    out = out.replace("((", "(")
    out = re.sub(r"\s*(?:—>|–>|-->|->)\s*", " — ", out)
    out = re.sub(r"\s*(?:--|–-|—-|-\s+-|[-–—]{2,})\s*", " — ", out)
    out = re.sub(
        r"(?i)\bTamid Kadima\s*[-–—]+\s*Always Forward\b",
        "Tamid Kadima — Always Forward",
        out,
    )
    # Surround en/em-dashes flanked by letters/quotes with spaces (preserve digit ranges like 1–5)
    out = re.sub(r"(?<=[A-Za-z)”\"'])\s*[–—]+\s*(?=[A-Za-z(“\"'])", " — ", out)
    out = re.sub(r"#\s*(\d+)", r"number \1", out)
    out = re.sub(r"\s*&\s*", " and ", out)
    out = re.sub(r"[!]+[?]+|[?]+[!]+", "?", out)
    out = re.sub(r"!{2,}", "!", out)
    out = re.sub(r"\?{2,}", "?", out)
    out = re.sub(r"!\s*\.", "!", out)
    out = re.sub(r"\?\s*\.", "?", out)
    out = re.sub(r",\s*\.", ".", out)
    out = re.sub(r"(?<!\.)\.\s*\.(?!\.)", ".", out)
    out = re.sub(r"\(\s+([^)]*?)\s+\)", r"(\1)", out)
    out = re.sub(r"\(\s+", "(", out)
    out = re.sub(r"\s+\)", ")", out)
    # Upcase standalone inline list letters like `(a)` -> `(A)` so TTS does not reduce 'a' to 'uh'
    out = re.sub(r"(?<=\s)\(([a-z])\)(?=[\s,.;:?!]|$)", lambda m: f"({m.group(1).upper()})", out)
    return out


def _format_bracket_span(inner: str, before: str, after: str) -> str:
    """Choose natural spoken phrasing for an editorial bracket or brace insertion."""
    inner = inner.strip()
    if not inner:
        return " "

    # Pure footnote / reference marker like [1] or [4B]
    if re.fullmatch(r"\d+[A-Za-z]?", inner):
        return ""

    before_stripped = before.rstrip()
    after_stripped = after.lstrip()
    word_count = len(inner.split())
    lower_inner = inner.lower()

    prev_words = re.findall(r"[A-Za-z]+", before_stripped.lower())
    prev_word = prev_words[-1] if prev_words else ""

    at_sentence_start = not before_stripped or before_stripped[-1] in ".!?—\"“”("
    preceded_by_glue = prev_word in _GLUE_PRECEDING_WORDS

    # Longer commentary notes
    if (
        word_count >= 5
        or lower_inner.startswith(("note:", "remember", "see "))
        or inner.endswith((".", "!", "?"))
        or ":" in inner
    ):
        if at_sentence_start:
            return f" {inner} "
        return f" — {inner} — "

    # Grammatical continuations (no extra pauses around words that complete syntax)
    if (
        lower_inner in _GLUE_INNER_WORDS
        or (word_count <= 4 and _PREP_PREFIX_RE.match(inner))
        or preceded_by_glue
        or (at_sentence_start and word_count <= 3)
    ):
        return f" {inner} "

    # Short parenthetical synonym / clarifier
    if "," in inner or ";" in inner:
        return f" — {inner} — "
    if after_stripped and after_stripped[0] in ",.;:?!\"”’)":
        return f", {inner}"
    return f", {inner}, "


def _expand_brackets(text: str) -> str:
    """Process square brackets and curly braces from innermost outward without 'meaning' clutter."""
    out = text
    innermost_re = re.compile(r"\[\s*([^\[\]{}]+?)\s*\]|\{\s*([^\[\]{}]+?)\s*\}")
    # Iterate to resolve nested brackets (up to 6 levels safely)
    for _ in range(6):
        m = innermost_re.search(out)
        if not m:
            break
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        before = out[: m.start()]
        after = out[m.end() :]
        replacement = _format_bracket_span(inner, before, after)
        out = f"{before}{replacement}{after}"

    # Strip any unmatched stray bracket characters (e.g. unclosed multi-paragraph [Note:)
    out = re.sub(r"[\[\]{}]", "", out)
    # Clean up punctuation collisions introduced by bracket unwrapping
    out = re.sub(r"—\s*,\s*", "— ", out)
    out = re.sub(r"—\s*([.;:?!])", r"—\1", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"(?:—\s*){2,}", " — ", out)
    out = re.sub(r"([.!?])\s*—\s*", r"\1 ", out)
    return out


def _expand_non_bible_abbreviations(text: str) -> str:
    """Protect Strong's numbers, page/verse/chapter refs, and prose abbreviations before citations."""
    out = re.sub(r"\bStrong[’']s\s+Heb\.?\s*(\d+)\b", r"Strong's Hebrew number \1", text)
    out = re.sub(r"\bStrong[’']s\s+(?:Gk|Grk)\.?\s*(\d+)\b", r"Strong's Greek number \1", out)
    out = re.sub(
        r"(?<!\w)(?:Pgs|pgs|PP|pp)\.\s*(\d+)\s*[-–—]\s*(\d+)\b",
        r"pages \1 through \2",
        out,
    )
    out = re.sub(r"(?<!\w)(?:Pgs|pgs|PP|pp)\.\s*(\d+)\b", r"pages \1", out)
    out = re.sub(
        r"(?<!\w)(?:Pg|pg|[Pp])\.\s*(\d+)\s*[-–—]\s*(\d+)\b",
        r"pages \1 through \2",
        out,
    )
    out = re.sub(r"(?<!\w)(?:Pg|pg|[Pp])\.\s*(\d+)\b", r"page \1", out)
    out = re.sub(r"\bvv\.\s*(\d+)\s*[-–—]\s*(\d+)\b", r"verses \1 through \2", out)
    out = re.sub(r"(?<!\w)[Vv]s?\.\s*(\d+)\s*[-–—]\s*(\d+)\b", r"verses \1 through \2", out)
    out = re.sub(r"(?<!\w)[Vv]\.\s*(\d+)\b", r"verse \1", out)
    out = re.sub(r"\b[Cc]h(?:ap)?\.\s*(\d+)\s*[-–—]\s*(\d+)\b", r"chapters \1 through \2", out)
    out = re.sub(r"\b[Cc]h(?:ap)?\.\s*(\d+)\b", r"chapter \1", out)
    out = re.sub(r"\bi\.\s*e\.", "that is,", out, flags=re.IGNORECASE)
    out = re.sub(r"\be\.\s*g\.", "for example,", out, flags=re.IGNORECASE)
    out = re.sub(r"\bibid\.", "from the same source.", out, flags=re.IGNORECASE)
    out = re.sub(r"\betc\.", "etcetera", out, flags=re.IGNORECASE)
    out = re.sub(r"\bvs\.(?=\s+[A-Za-z])", "versus", out, flags=re.IGNORECASE)
    return out


def _format_single_segment(
    tail: str,
    pos: int,
    is_psalm: bool,
    allow_dot_sep: bool,
    is_first: bool,
) -> tuple[str, int] | None:
    """Parse one Scripture segment (C1:V1-C2:V2, C:V1-V2, C:V, or chapter-only on first segment)."""
    sub = tail[pos:]
    # Omit leading 'Psalm' on first segment because spoken_book already supplies 'Psalm'/'Psalms'
    ch_prefix = "" if (is_psalm and is_first) else ("Psalm " if is_psalm else "chapter ")

    # 1. Cross-chapter range: C1:V1-C2:V2
    m = re.match(
        r"^(\d{1,3})\s*:\s*(\d{1,3}[a-zA-Z]?)\s*[-–—]\s*(\d{1,3})\s*:\s*(\d{1,3}[a-zA-Z]?)",
        sub,
    )
    if m:
        c1, v1, c2, v2 = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        if 1 <= c1 <= 150 and 1 <= c2 <= 150:
            end_ch = "Psalm" if is_psalm else "chapter"
            return f"{ch_prefix}{c1} verse {v1} through {end_ch} {c2} verse {v2}", pos + m.end()

    # 2. Double-colon typo: C:V1:V2 (e.g. 1 John 5:5:24)
    m = re.match(r"^(\d{1,3})\s*:\s*(\d{1,3}[a-zA-Z]?)\s*:\s*(\d{1,3}[a-zA-Z]?)", sub)
    if m:
        c, v1, v2 = int(m.group(1)), m.group(2), m.group(3)
        if 1 <= c <= 150:
            return f"{ch_prefix}{c}, verses {v1} and {v2}", pos + m.end()

    # 3. Same-chapter verse range: C:V1-V2 (or C.V1-V2 when allow_dot_sep, plus chained dashes 1:1-10-13)
    sep_pat = r"(?::|\.(?=\d))" if allow_dot_sep else r":"
    m = re.match(
        rf"^(\d{{1,3}})\s*{sep_pat}\s*(\d{{1,3}}[a-zA-Z]?)((?:\s*[-–—]\s*\d{{1,3}}[a-zA-Z]?)+)(?!\s*:)",
        sub,
    )
    if m:
        c = int(m.group(1))
        if 1 <= c <= 150:
            v1 = m.group(2)
            v_ends = re.findall(r"\d{1,3}[a-zA-Z]?", m.group(3))
            v_end = v_ends[-1]
            consumed = pos + m.end()
            # Optionally attach additional comma/and verses in same chapter (e.g. 20:10-12, 14)
            extra_verses: list[str] = []
            while True:
                rem = tail[consumed:]
                mv = re.match(r"^\s*(?:,\s*(?:and\s+)?|\s+and\s+)(\d{1,3}[a-zA-Z]?)\b(?!\s*[:.])", rem)
                if not mv or NUMBERED_BOOK_LOOKAHEAD_RE.match(rem[rem.find(mv.group(1)) :]):
                    break
                # Stop if `and <digits>` actually introduces another verse range of chapters like `and 2.1-47`
                after_num = rem[mv.end() :]
                if re.match(r"^\s*[-–—]", after_num):
                    break
                extra_verses.append(mv.group(1))
                consumed += mv.end()
            spoken = f"{ch_prefix}{c}, verses {v1} through {v_end}"
            if extra_verses:
                spoken += ", and " + ", ".join(extra_verses) if len(extra_verses) == 1 else ", " + ", ".join(extra_verses[:-1]) + f", and {extra_verses[-1]}"
            return spoken, consumed

    # 4. Single verse + optional same-chapter verse list (e.g. 20:10, 14, and 15)
    m = re.match(rf"^(\d{{1,3}})\s*{sep_pat}\s*(\d{{1,3}}[a-zA-Z]?)(?!\s*:)", sub)
    if m:
        c = int(m.group(1))
        if 1 <= c <= 150:
            verses = [m.group(2)]
            consumed = pos + m.end()
            while True:
                rem = tail[consumed:]
                mv = re.match(r"^\s*(?:,\s*(?:and\s+)?|\s+and\s+)(\d{1,3}[a-zA-Z]?)\b(?!\s*[:.])", rem)
                if not mv:
                    break
                digit_start = mv.start(1)
                if NUMBERED_BOOK_LOOKAHEAD_RE.match(rem[digit_start:]):
                    break
                # Stop if followed by dash (e.g. `1:3, 4-6` is handled cleanly only if not another book)
                if re.match(r"^\s*[-–—]", rem[mv.end() :]):
                    break
                verses.append(mv.group(1))
                consumed += mv.end()
            if len(verses) == 1:
                return f"{ch_prefix}{c} verse {verses[0]}", consumed
            if len(verses) == 2:
                return f"{ch_prefix}{c}, verses {verses[0]} and {verses[1]}", consumed
            return (
                f"{ch_prefix}{c}, verses " + ", ".join(verses[:-1]) + f", and {verses[-1]}",
                consumed,
            )

    # 5. Chapter-only range/list/single (only immediately after a Bible book)
    if is_first:
        # Chapter range: Ezek. 40-46
        m = re.match(r"^(\d{1,3})\s*[-–—]\s*(\d{1,3})\b(?!\s*(?::|\.\d))", sub)
        if m:
            c1, c2 = int(m.group(1)), int(m.group(2))
            if 1 <= c1 <= 150 and 1 <= c2 <= 150 and c2 > c1:
                prefix = "" if is_psalm else "chapters "
                return f"{prefix}{c1} through {c2}", pos + m.end()

        # Chapter pair: Revelation 2 and 3; Psalms 34 and 91; 1 Timothy 3 and 4
        m = re.match(r"^(\d{1,3})\s+and\s+(\d{1,3})\b(?!\s*(?::|\.\d)|\s+[A-Za-z])", sub)
        if m:
            c1, c2 = int(m.group(1)), int(m.group(2))
            if 1 <= c1 <= 150 and 1 <= c2 <= 150:
                prefix = "" if is_psalm else "chapters "
                return f"{prefix}{c1} and {c2}", pos + m.end()

        # Single chapter: 1 Cor. 14
        m = re.match(r"^(\d{1,3})\b(?!\s*(?::|\.\d))", sub)
        if m:
            c = int(m.group(1))
            if 1 <= c <= 150:
                return f"{ch_prefix}{c}", pos + m.end()

    return None


def _parse_citation_chain(tail: str, is_psalm: bool, book_had_punct: bool, raw_book: str) -> tuple[str, int] | None:
    """Parse one or more Scripture segments attached to a matched Bible book name."""
    first = _format_single_segment(tail, 0, is_psalm=is_psalm, allow_dot_sep=False, is_first=True)
    if first is None:
        return None

    first_text, pos = first
    has_colon_or_multi = ":" in tail[:pos] or "chapters" in first_text or "Psalms" in first_text

    # Prevent false positives on phrases like "Is 5 things", "Song 1 time", "Mark 2 points"
    if not has_colon_or_multi:
        # Single chapter only: require explicit book period OR non-ambiguous book + boundary/known suffix
        after_first = tail[pos:]
        looks_like_ref_boundary = bool(
            re.match(r"^\s*(?:$|[.,;:?!)”\"'\]]|\band\b|\bthrough\b)", after_first)
        )
        book_entry = _RAW_BOOK_TABLE.get(re.sub(r"\s+", " ", raw_book.lower()))
        requires_strong = book_entry[2] if book_entry else True
        if requires_strong and not book_had_punct:
            return None
        if not book_had_punct and not looks_like_ref_boundary:
            return None
        # Guard against "1945" years or "John 2 times"
        if re.match(r"^\s+[a-z]{2,}", after_first) and not re.match(
            r"^\s+(?:and|through|or|in\s+(?:the|his))\b", after_first
        ):
            return None

    segments = [first_text]
    if has_colon_or_multi:
        while True:
            rem = tail[pos:]
            sep_m = re.match(r"^(\s*(?:;\s*(?:and\s+)?|,\s*(?:and\s+)?|\s+and\s+))", rem)
            if not sep_m:
                break
            next_pos = pos + sep_m.end()
            # Ensure a comma only chains another chapter:verse (not plain chapter), and guard numbered books
            if NUMBERED_BOOK_LOOKAHEAD_RE.match(tail[next_pos:]):
                break
            sep_str = sep_m.group(1)
            allow_dot = ";" in sep_str or "and" in sep_str
            # Next segment MUST contain `:` (or `.` after `and`/`;`) so we never consume prose numbers
            if not re.match(r"^\d{1,3}\s*(?::|\.(?=\d))\s*\d{1,3}", tail[next_pos:]) if allow_dot else not re.match(r"^\d{1,3}\s*:\s*\d{1,3}", tail[next_pos:]):
                break
            nxt = _format_single_segment(tail, next_pos, is_psalm=is_psalm, allow_dot_sep=allow_dot, is_first=False)
            if nxt is None:
                break
            seg_text, pos = nxt
            segments.append(seg_text)

    if len(segments) == 1:
        return segments[0], pos
    if len(segments) == 2:
        return f"{segments[0]}, and {segments[1]}", pos
    return "; ".join(segments[:-1]) + f"; and {segments[-1]}", pos


def _expand_scripture_citations(text: str) -> str:
    """Expand Bible book abbreviations, chapter/verse citations, and translation codes."""
    # Step 1: Book + Citation chains (scanned left-to-right for exact boundary safety)
    parts: list[str] = []
    cursor = 0
    while cursor < len(text):
        m = BOOK_CITE_START_RE.search(text, cursor)
        if not m:
            parts.append(text[cursor:])
            break

        raw_book = m.group(1)
        trailing_punct = m.group(2)
        key = re.sub(r"\s+", " ", raw_book.lower()).replace("’", "'")
        entry = _RAW_BOOK_TABLE.get(key) or _RAW_BOOK_TABLE.get(re.sub(r"\s+", " ", raw_book.lower()))
        if entry is None:
            parts.append(text[cursor : m.end()])
            cursor = m.end()
            continue

        spoken_book, is_psalm, req_strong = entry
        # Ambiguous lowercase words like "in", "am", "is", "mark", "act" must be capitalized unless clear `:` follows
        tail = text[m.end() :]
        has_colon_ahead = bool(re.match(r"^\d{1,3}\s*:\s*\d", tail))
        if req_strong and raw_book.islower():
            parts.append(text[cursor : m.end()])
            cursor = m.end()
            continue
        if raw_book.islower() and not has_colon_ahead:
            parts.append(text[cursor : m.end()])
            cursor = m.end()
            continue

        parsed = _parse_citation_chain(tail, is_psalm=is_psalm, book_had_punct=bool(trailing_punct), raw_book=raw_book)
        if parsed is None:
            parts.append(text[cursor : m.end()])
            cursor = m.end()
            continue

        cite_speech, consumed = parsed
        parts.append(text[cursor : m.start()])
        parts.append(f"{spoken_book} {cite_speech}")
        cursor = m.end() + consumed

    out = "".join(parts)

    # Step 2: Standalone numbered books without explicit verse numbers (e.g. `1 Peter`, `2 Cor.`)
    def _repl_numbered_book(match: re.Match[str]) -> str:
        num = match.group(1)
        book_raw = match.group(2)
        book_full = _NUMBERED_BASE_BOOKS.get(book_raw.lower(), book_raw)
        if num == "3" and book_full != "John":
            return match.group(0)
        if book_raw.islower():
            return match.group(0)
        return f"{ORDINAL_WORDS[num]} {book_full}"

    out = STANDALONE_NUMBERED_BOOK_RE.sub(_repl_numbered_book, out)

    # Step 3: Standalone chapter:verse references without book name (e.g. (32:1), (6:9-8:22))
    out_parts: list[str] = []
    pos = 0
    standalone_re = re.compile(r"(?<![:\w])(\d{1,3})\s*:\s*(\d{1,3}[a-zA-Z]?)")
    while pos < len(out):
        m = standalone_re.search(out, pos)
        if not m:
            out_parts.append(out[pos:])
            break
        start = m.start()
        sub = out[start:]
        # Skip clock times (e.g. 7:30 am/p.m. or 12:30:45 p.m.)
        if re.match(
            r"^\d{1,3}\s*:\s*\d{1,2}(?:\s*:\s*\d{1,2})?\s*(?:a\.?m\.?|p\.?m\.?|hours?|o['’]clock)\b",
            sub,
            re.IGNORECASE,
        ):
            out_parts.append(out[pos : m.end()])
            pos = m.end()
            continue
        parsed = _format_single_segment(out, start, is_psalm=False, allow_dot_sep=False, is_first=False)
        if parsed is None:
            out_parts.append(out[pos : m.end()])
            pos = m.end()
            continue
        seg_text, end_pos = parsed
        out_parts.append(out[pos:start])
        out_parts.append(seg_text)
        pos = end_pos

    out = "".join(out_parts)

    # Step 4: Bible translation codes
    out = re.sub(r"(?<=\d)\s*,?\s*\bKJV\b", ", King James Version", out)
    out = re.sub(r"\bKJV\b", "King James Version", out)
    out = re.sub(r"(?<=\d)\s*,?\s*\bNASB\b", ", New American Standard Bible", out)
    out = re.sub(r"\bNASB\b", "New American Standard Bible", out)
    out = re.sub(r"\bNAS\s+Bible\b", "New American Standard Bible", out)
    out = re.sub(r"(?<=\d)\s*,?\s*\bNAS\b", ", New American Standard", out)
    out = re.sub(r"\bESV\s+Study\s+Version\b", "English Standard Version Study", out)
    out = re.sub(r"(?<=\d)\s*,?\s*\bESV\b", ", English Standard Version", out)
    out = re.sub(r"\bESV\b", "English Standard Version", out)
    out = re.sub(r"\bNIV\s+Study\s+Bible\b", "New International Version Study Bible", out)
    out = re.sub(r"(?<=\d)\s*,?\s*\bNIV\b", ", New International Version", out)
    out = re.sub(r"\bNIV\b", "New International Version", out)
    out = re.sub(r"(?<=\d)\s*,?\s*\bGNT\b", ", Good News Translation", out)
    # Collapse accidental duplicated chapter/Psalm when author wrote "Jeremiah ch. 3:11-18"
    out = re.sub(r"\b(chapter|psalm)\s+\1\b", r"\1", out, flags=re.IGNORECASE)
    return out


def _expand_slashes(text: str) -> str:
    """Convert readable slash pairs and fractions to natural spoken English."""
    out = re.sub(
        r"\b1/2\b(?=\s+(?:hour|hours|day|days|week|weeks|year|years|mile|miles|cup|cups|inch|inches|foot|feet|minute|minutes|second|seconds)\b)",
        "half",
        text,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\b1/2\b", "one half", out)
    out = re.sub(r"\b1/3\b", "one third", out)
    out = re.sub(r"\b1/4\b", "one quarter", out)
    out = re.sub(r"\b3/4\b", "three quarters", out)
    out = re.sub(r"(?i)\bPNW/CV/?", "Contender's Voice", out)
    out = re.sub(r"(?i)\bAI/Bible\b", "A I and Bible", out)
    out = re.sub(r"\bOrders/Comments\b", "Orders and Comments", out)
    out = re.sub(r"(?i)\band/or\b", "and or", out)
    out = re.sub(
        r"\b([A-Za-z]+)/([A-Za-z]+(?:[’']s)?)\b(?!(?:/|\.[A-Za-z]))",
        lambda m: m.group(0) if m.group(2).lower() in {"com", "org", "net", "edu", "gov"} else f"{m.group(1)} or {m.group(2)}",
        out,
    )
    return out


def _normalize_caps_and_states(text: str) -> str:
    """Expand divine names, ministry acronyms, U.S. state codes, and shouting headings."""
    out = re.sub(r"\bYHWH-Hoshe[’']ah\b", "Yahweh Hoshe'ah", text)
    out = re.sub(r"\b(?:YHWH|YHVH)([’']s)?\b", lambda m: "Yahweh" + (m.group(1) or ""), out)
    out = re.sub(r"\bADONAI([’']s)?\b", lambda m: "Adonai" + (m.group(1) or ""), out)
    out = re.sub(r"\bLORD([’']s)?\b", lambda m: "Lord" + (m.group(1) or ""), out)
    out = re.sub(r"\bC\.?V\.?(?=\s|[.,;:?!)]|$)", "Contender's Voice", out)
    out = re.sub(r"\bAAI\b", "AI", out)
    out = re.sub(r"\bPNW\b", "P N W", out)
    out = re.sub(r"\bNWO\b", "N W O", out)
    out = re.sub(r"\bWFA\b", "W F A", out)
    out = re.sub(r"\bUSS\b", "U S S", out)
    out = re.sub(r"\bUSF\b", "U S F", out)
    out = re.sub(r"\bBCE\b", "B C E", out)
    out = re.sub(r"(\d\s*|century\s+)\bCE\b", r"\1C E", out)
    out = re.sub(r"(\d\s*)\bBC\b", r"\1B C", out)

    # Expand city, STATE abbreviations so "Tulsa, OK." is not read as "Tulsa, okay"
    out = STATE_AFTER_CITY_RE.sub(lambda m: f"{m.group(1)}{US_STATES[m.group(2)]}", out)

    # Convert multi-word ALL-CAPS headings (e.g. "WHOSE PATH ARE YOU ON?") to title case
    def _title_caps_phrase(match: re.Match[str]) -> str:
        words = match.group(0).split()
        return " ".join(w if w in _KEEP_UPPER_IN_PHRASE else w.capitalize() for w in words)

    out = re.sub(r"\b[A-Z]{2,}(?:\s+[A-Z]{2,}){1,}\b", _title_caps_phrase, out)

    # Lowercase or capitalize isolated ALL-CAPS English emphasis words
    def _soften_single_cap(match: re.Match[str]) -> str:
        word = match.group(0)
        if word not in ALL_CAPS_EMPHASIS_WORDS:
            return word
        before = out[: match.start()].rstrip()
        if not before or before[-1] in ".!?\"“(":
            return word.capitalize()
        if word in {"NEW", "WAY", "GOD", "AUDIO"}:
            return word.capitalize()
        return word.lower()

    out = re.sub(r"\b[A-Z]{2,}\b", _soften_single_cap, out)
    return out


def _apply_pronunciations(text: str, pronunciations: Mapping[str, str]) -> str:
    """Apply longest-first, case-insensitive whole-word pronunciation replacements."""
    if not pronunciations:
        return text
    ordered = sorted(pronunciations.items(), key=lambda kv: len(kv[0]), reverse=True)
    for term, phonetic in ordered:
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags=re.IGNORECASE)
        text = pattern.sub(phonetic, text)
    return text


def _polish_punctuation(text: str) -> str:
    """Clean up minor punctuation/spacing artifacts after all expansions."""
    # Fix misplaced opening curly quote used as closing quote immediately after a word/punctuation
    out = re.sub(r"(?<=[A-Za-z0-9.,!?])“", "”", text)
    # Fix misplaced closing curly quote used as opening quote (preceded by space, followed by word)
    out = re.sub(r"(?<=\s)”(?=[A-Za-z0-9])", "“", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\s+([,.;:?!])", r"\1", out)
    out = re.sub(r"([,;:])(?=[A-Za-z“\"])", r"\1 ", out)
    out = re.sub(r"(?<!\d)([,;:])(?=\d)", r"\1 ", out)
    out = re.sub(r"“\s+", "“", out)
    out = re.sub(r"\s+”", "”", out)
    out = re.sub(r"(?<=[A-Za-z0-9.,!?])”(?=[A-Za-z])", "” ", out)
    out = re.sub(r"(?<=[a-z.,!?])\"(?=[a-z])", "\" ", out)
    out = re.sub(r"\(\s+", "(", out)
    out = re.sub(r"\s+\)", ")", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def normalize_for_speech(text: str, pronunciations: Mapping[str, str] | None = None) -> str:
    """Transform article prose, citations, brackets, and acronyms into natural speech text."""
    out = _strip_urls_and_meta(text or "")
    out = _normalize_typography(out)
    out = _expand_brackets(out)
    out = _expand_non_bible_abbreviations(out)
    out = _expand_scripture_citations(out)
    out = _expand_slashes(out)
    out = _normalize_caps_and_states(out)
    if pronunciations:
        out = _apply_pronunciations(out, pronunciations)
    return _polish_punctuation(out)
