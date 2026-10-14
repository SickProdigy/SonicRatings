"""Durable import processing without live providers or rating writes."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from sonicratings import automation as worker

RECORDING = "00000000-0000-4000-8000-000000000001"
TRACK = {"path": "/music/Artist/Album/Song.flac", "recording": RECORDING,
         "artist": "Artist", "album": "Album", "title": "Song", "album_artist": "Artist"}
SONG = {"id": "song", "path": "Artist/Album/Song.flac", "musicBrainzId": RECORDING,
        "artist": "Artist", "album": "Album", "title": "Song", "userRating": 0}


class Server:
    def __init__(self, *songs):
        self.data = {song["id"]: copy.deepcopy(song) for song in songs}
        self.scans = 0
    def songs(self):
        self.scans += 1
        return copy.deepcopy(self.data)
    def get_song(self, identity):
        return copy.deepcopy(self.data[identity])


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "jobs/job.json"
        worker.write_json(self.path, {"version": 1, "tracks": [TRACK]})
        self.options = SimpleNamespace(preview=False)
        self.server = Server(SONG)
        self.calls = []
    def rate(self, options, tracks):
        self.calls.extend(tracks)
        for track in tracks:
            if not options.preview:
                self.server.data[track["id"]]["userRating"] = 4
        return 0
    def run_worker(self, now=1000, runner=None):
        return worker.work(self.root, self.server, self.options, runner or self.rate, now)

    def test_delayed_import_retries_then_rates_verified_song(self):
        self.server.data = {}
        self.assertEqual(self.run_worker(), 0)
        self.assertTrue(self.path.exists())
        self.assertEqual(self.calls, [])
        self.server.data = {"song": copy.deepcopy(SONG)}
        self.assertEqual(self.run_worker(now=1100), 0)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.calls[0]["id"], "song")
    def test_existing_personal_rating_is_preserved(self):
        self.server.data["song"]["userRating"] = 2
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.path.exists())
    def test_ambiguous_and_conflicting_identity_stay_queued(self):
        for candidate in ({**SONG, "id": "other"}, {**SONG, "musicBrainzId": "00000000-0000-4000-8000-000000000002"}):
            with self.subTest(candidate=candidate):
                self.server = Server(SONG, candidate) if candidate["id"] == "other" else Server(candidate)
                worker.write_json(self.path, {"tracks": [TRACK]})
                self.assertEqual(self.run_worker(), 0)
                self.assertEqual(self.calls, [])
                self.assertTrue(self.path.exists())
    def test_identity_is_rechecked_after_scan(self):
        self.server.get_song = lambda _: {**SONG, "title": "Song (Live)"}
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.calls, [])
        self.assertTrue(self.path.exists())
    def test_preview_keeps_job_and_does_not_write_rating(self):
        self.options.preview = True
        before = self.path.read_bytes()
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.server.data["song"]["userRating"], 0)
        self.assertEqual(self.path.read_bytes(), before)
    def test_source_miss_retries_with_backoff(self):
        self.assertEqual(self.run_worker(runner=lambda *args: 0), 0)
        attempts = json.loads(self.path.read_text())["attempts"]
        self.assertEqual(attempts, 1)
        scans = self.server.scans
        self.assertEqual(self.run_worker(now=1001), 0)
        self.assertEqual(self.server.scans, scans)
    def test_failed_run_retains_job_and_retries(self):
        def fail(*args): raise RuntimeError("provider failed")
        self.assertEqual(self.run_worker(runner=fail), 1)
        self.assertTrue(self.path.exists())
        self.assertEqual(self.run_worker(now=1100), 0)
        self.assertFalse(self.path.exists())
    def test_corrupt_job_does_not_block_valid_work(self):
        corrupt = self.root / "jobs/corrupt.json"
        corrupt.write_text("invalid json")
        self.assertEqual(self.run_worker(), 1)
        self.assertFalse(self.path.exists())
        self.assertTrue(corrupt.exists())

    def test_scan_failure_retains_every_job(self):
        self.server.songs = Mock(side_effect=RuntimeError("server offline"))
        before = self.path.read_bytes()
        with self.assertRaises(RuntimeError): self.run_worker()
        self.assertEqual(self.path.read_bytes(), before)
    def test_invalid_track_or_retry_state_does_not_block_targeted_lookup(self):
        class TargetedServer(Server):
            def songs_for_tracks(self, tracks):
                return self.songs()
        for invalid in ({"tracks": [{}]}, {"tracks": [None]},
                        {"tracks": [TRACK], "attempts": "bad"},
                        {"tracks": [TRACK], "retry_after": float("nan")}):
            with self.subTest(job=invalid):
                self.server = TargetedServer(SONG)
                worker.write_json(self.path, {"tracks": [TRACK]})
                corrupt = self.root / "jobs/corrupt.json"
                worker.write_json(corrupt, invalid)
                before = corrupt.read_bytes()
                self.assertEqual(self.run_worker(), 1)
                self.assertFalse(self.path.exists())
                self.assertEqual(corrupt.read_bytes(), before)
    def test_queue_snapshot_is_local_and_duplicate_callback_preserves_retry(self):
        self.path.unlink()
        fetch = Mock(side_effect=[{"title": "Album", "foreignAlbumId": RECORDING}, [{"path": TRACK["path"]}]])
        tags = {"musicbrainz_trackid": [RECORDING], "musicbrainz_releasegroupid": [RECORDING],
                "artist": ["Artist"], "album": ["Album"], "title": ["Song"]}
        reader = lambda _: SimpleNamespace(tags=tags)
        self.assertEqual(worker.enqueue(self.root, 123, fetch, reader), 1)
        job = next((self.root / "jobs").glob("*.json"))
        data = json.loads(job.read_text()); data["retry_after"] = 5000
        worker.write_json(job, data)
        fetch.side_effect = [{"title": "Album", "foreignAlbumId": RECORDING}, [{"path": TRACK["path"]}]]
        self.assertEqual(worker.enqueue(self.root, 123, fetch, reader), 1)
        self.assertEqual(json.loads(job.read_text())["retry_after"], 5000)
    def test_worker_lock_prevents_concurrent_processing(self):
        with worker.worker_lock(self.root):
            with self.assertRaises(OSError):
                with worker.worker_lock(self.root): pass
    def test_import_candidate_lookup_is_paginated_and_does_not_scan_library(self):
        server = worker.Subsonic("https://nav.example.test", "user", "secret")
        calls = []
        def call(method, **params):
            calls.append((method, params))
            if method == "search3":
                albums = [{"id": "match", "name": "Album"}] + [{"id": str(i), "name": "Other"} for i in range(99)] if params["albumOffset"] == 0 else []
                return {"searchResult3": {"album": albums}}
            if method == "getAlbum":
                self.assertEqual(params["id"], "match")
                return {"album": {"artist": "Artist", "song": [SONG]}}
            self.fail("Unexpected library scan")
        server.call = call
        self.assertEqual(server.songs_for_tracks([TRACK])["song"]["musicBrainzId"], RECORDING)
        self.assertEqual([params["albumOffset"] for method, params in calls if method == "search3"], [0, 100])

    def test_state_is_scoped_to_server_and_user(self):
        self.assertEqual(worker.server_root(self.root, "https://nav/", "user"), worker.server_root(self.root, "https://nav", "user"))
        self.assertNotEqual(worker.server_root(self.root, "https://nav", "user"), worker.server_root(self.root, "https://nav", "other"))


if __name__ == "__main__":
    unittest.main()
