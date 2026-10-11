"""Conservative Last.fm spelling variants; never discard recording versions."""

import re
import unicodedata


VERSION_WORDS = re.compile(
    r"\b(?:remix|instrumental|edit|version|mix|karaoke|live|acoustic|demo|remaster(?:ed)?|extended)\b",
    re.IGNORECASE,
)


def clean_spelling(value):
    value = unicodedata.normalize("NFKC", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Cf")
    value = value.translate(str.maketrans({c: "-" for c in "‐‑‒–—−"}))
    value = value.translate(str.maketrans({c: "'" for c in "‘’ʼ"}))
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(value):
    value = clean_spelling(value).casefold().replace("'", "")
    value = re.sub(r"\bpart\b", "pt", value)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value)).strip()


def lookup_variants(artist, title):
    """Try originals first and deduplicate punctuation-only fallback queries."""
    artists = list(dict.fromkeys([artist, clean_spelling(artist)]))
    cleaned = clean_spelling(title)
    # Preserve the entire descriptor, including the remixer's name.
    without_notes = re.sub(
        r"\(([^)]*)\)|\[([^]]*)\]",
        lambda m: m.group(0) if VERSION_WORDS.search(m.group(0)) else "",
        cleaned,
    )
    titles = [title, cleaned, without_notes]
    for candidate in list(titles):
        titles.append(re.sub(r"\s+\+\s+", " ", candidate))
        titles.append(re.sub(r"\bPart\b", "Pt.", candidate, flags=re.IGNORECASE))
    # Catalogs sometimes omit apostrophes or use spaces instead of punctuation.
    for candidate in list(titles):
        titles.append(candidate.replace("'", ""))
        titles.append(re.sub(r"[^\w\s]", " ", candidate.replace("'", "")))
    titles = list(dict.fromkeys(re.sub(r"\s+", " ", t).strip() for t in titles if t.strip()))
    return [(a, t) for a in artists for t in titles]


def matches_track(track, artist, title):
    """Reject autocorrections to a different title, artist, or recording version."""
    if normalize_title(track.get("name", "")) != normalize_title(title):
        return False
    returned_artist = track.get("artist")
    if isinstance(returned_artist, dict):
        returned_artist = returned_artist.get("name")
    return not returned_artist or normalize_title(returned_artist) == normalize_title(artist)
