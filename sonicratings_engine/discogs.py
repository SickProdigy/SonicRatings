"""Read-only Discogs release ratings, usable without starting a library sync."""
import math
import re
import time
import unicodedata

import requests


class DiscogsError(RuntimeError):
    """A provider failure, distinct from an absent match or rating."""


def normalized(value):
    # Keep version/edition words: a live track is not its studio version.
    return " ".join(re.sub(r"[\W_]+", " ", unicodedata.normalize(
        "NFKC", str(value)).casefold()).split())


def artist_names(credits):
    names = set()
    for credit in credits:
        for field in ("name", "anv"):
            name = credit.get(field, "")
            if name:
                # Discogs adds numbered suffixes to distinguish artist identities.
                name = normalized(re.sub(r"\s+\(\d+\)$", "", name))
                names.add(name)
                if name == "various":
                    names.add("various artists")
    return names


def positive_id(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9]\d*", str(value)):
        raise ValueError("Discogs release IDs must be positive integers")
    return int(value)


def release_rating(release, min_votes=5):
    """Return a native 1–5 release average and vote count, or no usable rating."""
    community = release.get("community") or {}
    rating = community.get("rating") or {}
    if not isinstance(rating, dict):
        return None
    average, count = rating.get("average"), rating.get("count")
    if (isinstance(average, bool) or not isinstance(average, (int, float))
            or not math.isfinite(average) or not 1 <= average <= 5
            or isinstance(count, bool) or not isinstance(count, int)
            or count < max(1, min_votes)):
        return None
    return {"average": average, "votes": count, "rating": int(average + .5)}


def tracks(tracklist):
    for track in tracklist:
        if track.get("sub_tracks"):
            yield from tracks(track["sub_tracks"])
        elif track.get("type_", "track") == "track":
            yield track


class DiscogsClient:
    """Cache album lookups; never send rating writes to Discogs or Subsonic."""
    def __init__(self, token="", min_votes=5, session=None):
        if isinstance(min_votes, bool) or not isinstance(min_votes, int) or min_votes < 1:
            raise ValueError("Discogs minimum votes must be a positive integer")
        self.min_votes = min_votes
        self.session = session if session is not None else requests.Session()
        self.headers = {"User-Agent": "SonicRatings (https://gitea.rcs1.top/sickprodigy/SonicRatings)",
                        "Accept": "application/json"}
        if token:
            if "\n" in token or "\r" in token:
                raise ValueError("Invalid Discogs token")
            self.headers["Authorization"] = "Discogs token=" + token
        self.interval = 60 / (60 if token else 25) + .05
        self.next_request = 0
        self.resources = {}
        self.albums = {}

    def _get(self, path, **params):
        key = (path, tuple(sorted(params.items())))
        if key in self.resources:
            return self.resources[key]
        for attempt in range(3):
            time.sleep(max(0, self.next_request - time.monotonic()))
            request_started = time.monotonic()
            self.next_request = request_started + self.interval
            try:
                response = self.session.get("https://api.discogs.com/" + path,
                    params=params, headers=self.headers, timeout=(10, 30))
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise DiscogsError("Discogs connection failed after retries") from None
                self.next_request = max(self.next_request, time.monotonic() + 2 ** (attempt + 1))
                continue
            try:
                limit = float(response.headers.get("X-Discogs-Ratelimit", 0))
                if math.isfinite(limit) and limit > 0:
                    self.interval = max(self.interval, 60 / limit + .05)
            except (ValueError, TypeError):
                pass
            self.next_request = max(self.next_request, request_started + self.interval)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2:
                    raise DiscogsError("Discogs service failed (HTTP %s)" % response.status_code)
                try:
                    delay = float(response.headers.get("Retry-After", 60 if response.status_code == 429 else 2 ** (attempt + 1)))
                    if not math.isfinite(delay) or delay < 0:
                        raise ValueError()
                except (ValueError, TypeError):
                    delay = 60 if response.status_code == 429 else 2 ** (attempt + 1)
                self.next_request = max(self.next_request, time.monotonic() + delay)
                continue
            if response.status_code == 404:
                self.resources[key] = {}
                return {}
            if response.status_code in (401, 403):
                raise DiscogsError("Discogs access denied; check DISCOGS_TOKEN and API access")
            if not response.ok:
                raise DiscogsError("Discogs request failed (HTTP %s)" % response.status_code)
            try:
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError()
            except ValueError:
                raise DiscogsError("Discogs returned invalid JSON") from None
            self.next_request = max(self.next_request, time.monotonic())
            self.resources[key] = data
            return data
        raise DiscogsError("Discogs lookup failed")

    @staticmethod
    def _matches(resource, artist, album):
        return (normalized(resource.get("title", "")) == normalized(album)
                and normalized(artist) in artist_names(resource.get("artists", [])))

    def _search(self, kind, artist, album):
        data = self._get("database/search", type=kind, artist=artist,
                         release_title=album, per_page=25, page=1)
        results = data.get("results", [])
        # Do not infer uniqueness from a truncated page or select an arbitrary hit.
        if len(results) > 5 or data.get("pagination", {}).get("pages", 1) > 1:
            return None
        matched = {}
        for item in results:
            if item.get("type") != kind:
                continue
            identity = positive_id(item["id"])
            detail = self._get(("masters/" if kind == "master" else "releases/") + str(identity))
            if self._matches(detail, artist, album):
                matched[identity] = detail
        return matched

    def find_release(self, artist, album, release_id=None):
        if not normalized(artist) or not normalized(album):
            return None
        explicit = positive_id(release_id) if release_id is not None else None
        key = (normalized(artist), normalized(album), explicit)
        if key in self.albums:
            return self.albums[key]
        selection, release = "explicit edition", None
        if explicit is not None:
            release = self._get("releases/" + str(explicit))
        else:
            masters = self._search("master", artist, album)
            if masters is None or len(masters) > 1:
                self.albums[key] = None
                return None
            if masters:
                master_id, master = next(iter(masters.items()))
                release = self._get("releases/" + str(positive_id(master["main_release"])))
                if release.get("master_id") != master_id:
                    release = None
                selection = "master main release"
            else:
                releases = self._search("release", artist, album)
                if releases is not None and len(releases) == 1:
                    _, release = next(iter(releases.items()))
                selection = "unique release"
        result = None
        if release and self._matches(release, artist, album):
            rating = release_rating(release, self.min_votes)
            if rating:
                result = {**rating, "release_id": positive_id(release["id"]),
                          "master_id": release.get("master_id"), "title": release["title"],
                          "selection": selection, "scope": "release", "release": release}
        self.albums[key] = result
        return result

    def find_track(self, artist, title, album, album_artist=None, release_id=None):
        release = self.find_release(album_artist or artist, album, release_id)
        if not release or not normalized(title):
            return None
        for track in tracks(release["release"].get("tracklist", [])):
            if normalized(title) != normalized(track.get("title", "")):
                continue
            credits = track.get("artists") or release["release"].get("artists", [])
            if normalized(artist) not in artist_names(credits):
                continue
            return {key: value for key, value in release.items() if key != "release"} | {
                "matched_title": track["title"], "source": "discogs-release"}
        return None
