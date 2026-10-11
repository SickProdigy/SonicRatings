"""Import-safe rating engine for automation and future SonicRatings interfaces."""
from __future__ import annotations
import math
import time
import unicodedata
import uuid
import requests

def mbid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return ""

def normalized(value):
    # Preserve version qualifiers (live, remix, acoustic) rather than merging versions.
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())

def score_lastfm(listeners, plays, rank):
    """Same rank/reach/engagement formula and selective stars as the SonicRatings fork."""
    position = max(0, 100 - math.log2(rank) * 10) if rank else 0
    reach = min(90, math.log10(listeners + 1) * 13) if listeners and plays else 0
    engagement = min(12, math.log2(plays / listeners) * 4) if listeners and plays else 0
    score = round(min(100, position * .50 + reach * .40 + engagement * .10))
    bucket = sum(score >= threshold for threshold in (16.66, 33.33, 50, 66.66, 83.33))
    if score >= 80 and rank and rank <= 3 and listeners >= 100000:
        return 5
    if score >= 65:
        return 4
    return min(3, bucket)

class RatingProvider:
    def __init__(self, mb, key=""):
        self.mb, self.key = mb, key
        self.artists = {}
        self.session = requests.Session()
        self.next_request = 0

    def lastfm(self, method, **params):
        # Keep errors and credentials out of logs; transient failures retry next worker run.
        time.sleep(max(0, self.next_request - time.monotonic()))
        self.next_request = time.monotonic() + .25
        response = self.session.get("https://ws.audioscrobbler.com/2.0/", params={
            "method": method, "api_key": self.key, "format": "json", **params}, timeout=(10, 30))
        if not response.ok:
            raise RuntimeError(f"Last.fm returned HTTP {response.status_code}")
        data = response.json()
        if data.get("error"):
            if data["error"] == 6:
                return {}
            raise RuntimeError(f"Last.fm failed (code {data['error']})")
        return data

    def rating(self, track):
        if not self.key:
            data = self.mb.request(f"recording/{track['recording']}", inc="ratings")
            value = (data.get("rating") or {}).get("value")
            if value is None:
                return None
            value = float(value)
            if not math.isfinite(value) or not 0 <= value <= 5:
                return None
            return max(0, min(5, int(value + .5))), "musicbrainz"
        data = self.lastfm("track.getInfo", mbid=track["recording"])
        entry = data.get("track")
        if not entry:
            entry = self.lastfm("track.getInfo", artist=track["artist"], track=track["title"],
                                autocorrect=0).get("track")
        if not entry:
            return None
        artist = entry.get("artist", {})
        artist_name = artist.get("name", "") if isinstance(artist, dict) else artist
        if (normalized(entry.get("name", "")) != normalized(track["title"]) or
                normalized(artist_name) != normalized(track["artist"])):
            return None
        returned_id = mbid(entry.get("mbid"))
        if returned_id and returned_id != track["recording"]:
            return None
        listeners = max(0, int(entry.get("listeners", 0)))
        plays = max(0, int(entry.get("playcount", 0)))
        artist_key = normalized(artist_name)
        if artist_key not in self.artists:
            rows = self.lastfm("artist.getTopTracks", artist=artist_name, autocorrect=0,
                               limit=500).get("toptracks", {}).get("track", [])
            self.artists[artist_key] = {normalized(row["name"]): (index + 1, row)
                                       for index, row in reversed(list(enumerate(rows)))}
        match = self.artists[artist_key].get(normalized(track["title"]))
        rank = None
        if match:
            rank, row = match
            listeners = max(listeners, int(row.get("listeners", 0)))
            plays = max(plays, int(row.get("playcount", 0)))
        if not listeners or not plays:
            return None
        return score_lastfm(listeners, plays, rank), "lastfm"
