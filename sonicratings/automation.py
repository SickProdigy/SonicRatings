"""Queue Lidarr imports and rate their verified Subsonic songs after the server scan."""
from contextlib import contextmanager, nullcontext
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import tempfile
import time
import unicodedata
import uuid

import mutagen
import requests
from dotenv import load_dotenv

from . import cli


def normalized(value):
    return " ".join(unicodedata.normalize("NFC", str(value)).casefold().split())


def mbid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return ""


def settings():
    return ((os.getenv("SUBSONIC_URL") or os.getenv("NAV_BASE_URL", "")).rstrip("/"),
            os.getenv("SUBSONIC_USERNAME") or os.getenv("NAV_USER", ""),
            os.getenv("SUBSONIC_PASSWORD") or os.getenv("NAV_PASS", ""))


def server_root(directory, url, username):
    identity = hashlib.sha256(json.dumps([url.rstrip("/"), username]).encode()).hexdigest()[:16]
    return Path(directory) / identity


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        json.dump(data, handle)
        temporary = handle.name
    os.replace(temporary, path)


@contextmanager
def worker_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "worker.lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Subsonic:
    def __init__(self, url, username, password):
        if not (url.startswith(("http://", "https://")) and username and password):
            raise ValueError("Configure the Subsonic server and account")
        self.url, self.username, self.password = url.rstrip("/"), username, password
        self.session = requests.Session()

    def call(self, endpoint, **params):
        salt = secrets.token_hex(12)
        auth = {"u": self.username, "s": salt,
                "t": hashlib.md5((self.password + salt).encode()).hexdigest(),
                "v": "1.16.1", "c": "sonicratings", "f": "json"}
        try:
            response = self.session.get(f"{self.url}/rest/{endpoint}", params={**params, **auth}, timeout=(10, 45))
            if not response.ok:
                raise ValueError("Server request failed")
            result = response.json()["subsonic-response"]
            if result.get("status") != "ok":
                raise ValueError("Server request failed")
            return result
        except (requests.RequestException, ValueError, KeyError):
            raise RuntimeError("Subsonic request failed; queued work retained") from None

    def songs(self):
        result, offset = {}, 0
        while True:
            albums = self.call("getAlbumList2", type="alphabeticalByName", size=500, offset=offset).get("albumList2", {}).get("album", [])
            for album in albums:
                info = self.call("getAlbum", id=album["id"])["album"]
                for song in info.get("song", []):
                    result[str(song["id"])] = {**song, "albumArtist": info.get("artist", song.get("artist", ""))}
            if len(albums) < 500:
                return result
            offset += len(albums)

    def songs_for_tracks(self, tracks):
        """Search imported album candidates instead of scanning the whole library."""
        result, fetched = {}, set()
        for title in sorted({track["album"] for track in tracks}):
            offset = 0
            while True:
                candidates = self.call("search3", query=title, artistCount=0, songCount=0,
                                       albumCount=100, albumOffset=offset).get("searchResult3", {}).get("album", [])
                for candidate in candidates:
                    identity = str(candidate["id"])
                    if identity in fetched or normalized(candidate.get("name", "")) != normalized(title):
                        continue
                    fetched.add(identity)
                    album = self.call("getAlbum", id=identity)["album"]
                    for song in album.get("song", []):
                        result[str(song["id"])] = {**song, "albumArtist": album.get("artist", song.get("artist", ""))}
                if len(candidates) < 100:
                    break
                offset += len(candidates)
        return result

    def get_song(self, song_id):
        return self.call("getSong", id=song_id)["song"]


def enqueue(root, album_id, fetch=None, read_tags=None):
    if fetch is None:
        session = requests.Session()
        session.headers["X-Api-Key"] = os.environ["LIDARR_API_KEY"]

        def fetch(endpoint):
            try:
                response = session.get(f"{os.environ['LIDARR_URL'].rstrip('/')}/api/v1/{endpoint}", timeout=(10, 30))
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError):
                raise RuntimeError("Lidarr snapshot failed") from None
    album = fetch(f"album/{album_id}")
    files = fetch(f"trackfile?albumId={album_id}")
    read_tags = read_tags or (lambda path: mutagen.File(path, easy=True))
    tracks = []
    for item in files:
        audio = read_tags(item["path"])
        tags = getattr(audio, "tags", None) or {}

        def first(key, default=""):
            values = tags.get(key, [])
            return values if isinstance(values, str) else (values[0] if values else default)
        group = mbid(first("musicbrainz_releasegroupid"))
        if group and group != mbid(album.get("foreignAlbumId")):
            continue
        track = {"path": item["path"], "recording": mbid(first("musicbrainz_trackid")),
                 "artist": first("artist"), "title": first("title"),
                 "album": first("album", album.get("title", "")),
                 "album_artist": first("albumartist", first("artist"))}
        if track["artist"] and track["title"] and track["album"]:
            tracks.append(track)
    if not tracks:
        return 0
    job = {"version": 1, "album_id": str(album_id), "tracks": sorted(tracks, key=lambda row: row["path"])}
    digest = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()
    destination = root / "jobs" / f"{digest}.json"
    if not destination.exists():
        write_json(destination, job)
    return len(tracks)


def find_song(track, songs):
    matches = []
    for song in songs.values():
        recording = mbid(song.get("musicBrainzId"))
        if track.get("recording") and recording and track["recording"] != recording:
            continue
        if any(normalized(song.get(key, "")) != normalized(track[key]) for key in ("artist", "album", "title")):
            continue
        local = str(track.get("path", "")).replace("\\", "/")
        remote = str(song.get("path", "")).replace("\\", "/").lstrip("/")
        path_match = remote and (local.lstrip("/") == remote or local.endswith("/" + remote))
        if path_match or (track.get("recording") and recording == track["recording"]):
            matches.append(song)
    return matches[0] if len(matches) == 1 else None


def stars(song):
    value = song.get("userRating", 0) or 0
    number = int(value)
    if not 0 <= number <= 5 or float(value) != number:
        raise ValueError("Invalid personal rating")
    return number


def work(root, server, options, runner=cli.execute, now=None):
    now = time.time() if now is None else now
    jobs = sorted((root / "jobs").glob("*.json"))
    due, failures = [], 0
    for path in jobs:
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(job.get("tracks"), list):
                raise ValueError("Invalid queue job")
            if any(not isinstance(track, dict) or
                   any(not isinstance(track.get(key), str) or not track[key].strip()
                       for key in ("artist", "album", "title"))
                   for track in job["tracks"]):
                raise ValueError("Invalid queue track")
            attempts = job.get("attempts", 0)
            retry_after = job.get("retry_after", 0)
            if (type(attempts) is not int or attempts < 0 or
                    type(retry_after) not in (int, float) or
                    not 0 <= retry_after < float("inf")):
                raise ValueError("Invalid queue retry state")
            if job.get("retry_after", 0) <= now:
                due.append((path, job))
        except (ValueError, TypeError, AttributeError):
            logging.warning("Invalid SonicRatings job retained; other jobs continue")
            failures += 1
    if not due:
        return failures
    if callable(getattr(type(server), "songs_for_tracks", None)):
        songs = server.songs_for_tracks([track for _, job in due for track in job["tracks"]])
    else:
        songs = server.songs()
    for path, job in due:
        remaining = []
        selected_tracks = []
        resolved_tracks = []
        try:
            for track in job["tracks"]:
                song = find_song(track, songs)
                if song is None:
                    remaining.append(track)
                    continue
                latest = server.get_song(str(song["id"]))
                if find_song(track, {str(latest["id"]): latest}) is None:
                    remaining.append(track)
                    continue
                if stars(latest):
                    continue
                selected = {**track, "id": str(latest["id"]),
                            "recording": mbid(latest.get("musicBrainzId")) or track.get("recording", "")}
                selected_tracks.append(selected)
                resolved_tracks.append(track)
            if selected_tracks:
                runner(options, selected_tracks)
            for track, selected in zip(resolved_tracks, selected_tracks):
                if options.preview or not stars(server.get_song(selected["id"])):
                    remaining.append(track)
            if not options.preview:
                if remaining:
                    logging.info("SonicRatings: %s tracks awaiting a verified import or usable rating; retry scheduled", len(remaining))
                    attempts = min(job.get("attempts", 0) + 1, 7)
                    write_json(path, {**job, "tracks": remaining, "attempts": attempts,
                                     "retry_after": now + min(3600, 60 * 2 ** (attempts - 1))})
                else:
                    path.unlink()
        except (Exception, SystemExit):
            logging.warning("SonicRatings job failed; retained for retry")
            failures += 1
            if not options.preview:
                attempts = min(job.get("attempts", 0) + 1, 7)
                write_json(path, {**job, "attempts": attempts,
                                 "retry_after": now + min(3600, 60 * 2 ** (attempts - 1))})
    return failures


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("enqueue", "work", "library"))
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--album-id", type=int)
    parser.add_argument("--provider", choices=("spotify", "lastfm", "musicbrainz", "tidal", "discogs"), default="musicbrainz")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--discogs-inherit-album-rating", action="store_true")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)
    if args.env_file.is_file():
        load_dotenv(args.env_file)
    url, username, password = settings()
    root = server_root(args.state_dir, url, username)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "enqueue":
            if not (url and username) or not args.album_id or args.album_id < 1:
                parser.error("enqueue requires a configured server/account and positive --album-id")
            count = enqueue(root, args.album_id)
            logging.info("Queued %s tracks for SonicRatings", count)
            return 0
        server = Subsonic(url, username, password)
        # All automatic writes preserve personal ratings, regardless of provider.
        os.environ.update(NAV_BASE_URL=url, NAV_USER=username, NAV_PASS=password)
        flags = ["--provider", args.provider, "--unrated-only", "--log-dir", str(root), "--env-file", str(args.env_file)]
        if args.preview:
            flags.append("--preview")
        if args.discogs_inherit_album_rating:
            flags.append("--discogs-inherit-album-rating")
        options = cli.parse_args(flags)
        options.provenance_file = root / "generated-ratings.json"
        request_gate = os.getenv("MUSICBRAINZ_REQUEST_LOCK_DIR")
        gate = worker_lock(Path(request_gate)) if args.provider == "musicbrainz" and request_gate else nullcontext()
        with worker_lock(root), gate:
            if args.command == "library":
                tracks = [{"id": str(song["id"]), "artist": song.get("artist", ""),
                           "title": song.get("title", ""), "album": song.get("album", ""),
                           "album_artist": song.get("albumArtist", song.get("artist", "")),
                           "recording": mbid(song.get("musicBrainzId")), "path": song.get("path", "")} for song in server.songs().values()]
                return cli.execute(options, tracks)
            return 1 if work(root, server, options) else 0
    except (Exception, SystemExit):
        logging.error("SonicRatings automation failed; check configuration and server availability. Jobs retained.")
        return 1
