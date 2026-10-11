"""TIDAL catalog lookup using the public v2 API and app credentials."""

import math
import re
import time

import requests


def normalize(value):
    return re.sub(r"[\W_]+", " ", value.casefold()).strip()


def popularity_score(track):
    value = track.get("attributes", {}).get("popularity")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return value * 100


class TidalClient:
    def __init__(self, client_id, client_secret, country_code="US"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.country_code = country_code
        self.token = None
        self.expires_at = 0

    def _request(self, method, url, **kwargs):
        for attempt in range(3):
            try:
                response = requests.request(method, url, timeout=20, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        try:
                            delay = float(response.headers.get("Retry-After", 2 * (attempt + 1)))
                        except ValueError:
                            delay = 2 * (attempt + 1)
                        time.sleep(max(0, min(delay, 60)))
                        continue
                response.raise_for_status()
                return response.json()
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))

    def _authenticate(self):
        data = self._request(
            "POST", "https://auth.tidal.com/v1/oauth2/token",
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
        )
        self.token = data["access_token"]
        lifetime = float(data["expires_in"])
        self.expires_at = time.time() + lifetime - min(60, lifetime / 2)

    def get(self, path, **params):
        if self.token is None or time.time() >= self.expires_at:
            self._authenticate()
        params["countryCode"] = self.country_code
        for attempt in range(2):
            try:
                return self._request(
                    "GET", "https://openapi.tidal.com/v2/" + path,
                    headers={"Authorization": f"Bearer {self.token}",
                             "Accept": "application/vnd.api+json"},
                    params=params,
                )
            except requests.HTTPError as error:
                if error.response.status_code != 401 or attempt == 1:
                    raise
                self._authenticate()

    def find_track(self, artist, title, album):
        # Search results contain relationship identifiers and included resources.
        # Resolve those identifiers rather than assuming the first hit is correct.
        result = self.get("searchResults", **{
            "filter[query]": f"{artist} {title}", "include": "tracks",
        })
        roots = result.get("data", [])
        if isinstance(roots, dict):
            roots = [roots]
        identifiers = [item for root in roots
                       for item in root.get("relationships", {}).get("tracks", {}).get("data", [])]
        included = {(item["type"], item["id"]): item
                    for item in result.get("included", [])}
        candidates = []
        for identifier in identifiers:
            track = included.get((identifier["type"], identifier["id"]))
            if not track:
                track = self.get(f"tracks/{identifier['id']}").get("data", {})
            attributes = track.get("attributes", {})
            version = attributes.get("version")
            titles = [attributes.get("title", "")]
            if version:
                titles = [f"{titles[0]} {version}"]
            if normalize(title) not in [normalize(value) for value in titles]:
                continue
            # Fetch artist/album metadata to reject covers and prefer the same album.
            detail = self.get(f"tracks/{identifier['id']}", include="artists,albums")
            track = detail.get("data", {})
            related = {(item["type"], item["id"]): item
                       for item in detail.get("included", [])}
            relationships = track.get("relationships", {})
            def names(relationship):
                return [related.get((item["type"], item["id"]), {}).get("attributes", {})
                        for item in relationships.get(relationship, {}).get("data", [])]
            if not any(normalize(item.get("name", "")) == normalize(artist)
                       for item in names("artists")):
                continue
            score = popularity_score(track)
            if score is None:
                continue
            same_album = any(normalize(item.get("title", "")) == normalize(album)
                             for item in names("albums"))
            candidates.append((same_album, track))
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[0])[1]
