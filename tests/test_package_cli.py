"""Exercise the packaged sync with fake provider and Subsonic APIs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlparse, parse_qs

from sonicratings import cli, __version__


class PackageCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = Path.cwd()
        os.chdir(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(os.chdir, self.previous)
        self.environment = patch.dict(os.environ, {
            "NAV_BASE_URL": "https://nav.example.test", "NAV_USER": "test", "NAV_PASS": "secret"
        }, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.rating = 0
        self.writes = []
        self.provider = Mock()
        self.provider.find_track.return_value = {
            "average": 4.2, "rating": 4, "matched_title": "Song",
            "release_id": 10, "selection": "exact", "votes": 20,
        }

    def request(self, url, **kwargs):
        method = urlparse(url).path.rsplit("/", 1)[-1]
        if method == "getAlbum":
            body = {"album": {"id": "album", "name": "Album", "artist": "Artist", "artistId": "artist",
                "song": [{"id": "song", "title": "Song", "album": "Album"}]}}
        elif method == "getSong":
            body = {"song": {"id": "song", "userRating": self.rating, "artist": "Artist", "album": "Album", "title": "Song", "path": "Artist/Album/Song.flac", "musicBrainzId": "00000000-0000-4000-8000-000000000001"}}
        elif method == "setRating":
            self.writes.append(parse_qs(urlparse(url).query))
            body = {}
        elif method == "getArtists":
            body = {"artists": {"index": [{"artist": [{"id": "artist", "name": "Artist"}]}]}}
        elif method == "getArtist":
            body = {"artist": {"name": "Artist", "album": [{"id": "album", "name": "Album"}]}}
        else:
            raise AssertionError("Unexpected network request: " + method)
        payload = {"subsonic-response": {"status": "ok", **body}}
        response = Mock(status_code=200, text=json.dumps(payload))
        response.json.return_value = payload
        return response

    def sync(self, *options):
        with patch.object(cli.requests, "get", side_effect=self.request), patch.object(cli, "DiscogsClient", return_value=self.provider):
            return cli.main(["--provider", "discogs", "--lock-duration", "0", *options])

    def test_preview_reads_library_without_writing_ratings_or_locks(self):
        self.assertEqual(self.sync("--preview"), 0)
        self.provider.find_track.assert_called_once()
        self.assertEqual(self.writes, [])
        self.assertFalse(Path("logs/song_update_lock.json").exists())
        self.assertEqual(cli.TOTAL_TRACKS, 1)

    def test_album_sync_writes_rating_and_preserves_existing_lock_history(self):
        directory = Path("runtime")
        directory.mkdir()
        (directory / "song_update_lock.json").write_text(json.dumps({"older-song": {"updated_at": 100}}))
        self.assertEqual(self.sync("--album", "album", "--discogs-inherit-album-rating", "--log-dir", str(directory)), 0)
        self.assertEqual([write["rating"] for write in self.writes], [["4"]])
        state = json.loads((directory / "song_update_lock.json").read_text())
        self.assertIn("older-song", state)
        self.assertEqual(state["song"]["track_name"], "Song")
        self.assertFalse(Path("logs").exists())

    def test_unrated_only_skips_existing_rating_before_provider_lookup(self):
        self.rating = 3
        self.assertEqual(self.sync("--album", "album", "--unrated-only", "--discogs-inherit-album-rating"), 0)
        self.provider.find_track.assert_not_called()
        self.assertEqual(self.writes, [])
        self.assertEqual(cli.SKIPPED_RATED, 1)

    def test_multiple_runs_reset_counters_and_close_run_log(self):
        for _ in range(2):
            self.assertEqual(self.sync("--album", "album", "--preview"), 0)
            self.assertEqual(cli.TOTAL_TRACKS, 1)
            self.assertTrue(cli.file_handler._closed)

    def test_import_help_and_version_are_safe_outside_repository(self):
        repository = str(self.previous)
        code = """import sys
sys.path.insert(0, sys.argv[1])
from unittest.mock import patch
with patch('requests.get', side_effect=AssertionError('network')), patch('requests.post', side_effect=AssertionError('network')):
 import sonicratings.cli
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, repository], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(Path("logs").exists())
        for options in (["--help"], ["--version"]):
            run = "import sys; sys.path.insert(0,sys.argv.pop(1)); from sonicratings.cli import main; raise SystemExit(main())"
            result = subprocess.run([sys.executable, "-I", "-B", "-c", run, repository, *options], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(__version__, result.stdout)
        self.assertFalse(Path("logs").exists())

    def test_queued_write_records_source_and_identity_before_server_write(self):
        recording = "00000000-0000-4000-8000-000000000001"
        options = cli.parse_args(["--provider", "discogs", "--unrated-only", "--discogs-inherit-album-rating"])
        options.provenance_file = Path("logs/generated-ratings.json")
        selected = {"id": "song", "recording": recording, "artist": "Artist", "album": "Album", "title": "Song", "path": "Artist/Album/Song.flac"}
        original = self.request
        def request(url, **kwargs):
            if urlparse(url).path.endswith("setRating"):
                provenance = json.loads(options.provenance_file.read_text())["song"]
                self.assertTrue(provenance["pending"])
                self.assertEqual(provenance["recording"], recording)
            return original(url, **kwargs)
        with patch.object(cli.requests, "get", side_effect=request), patch.object(cli, "DiscogsClient", return_value=self.provider):
            self.assertEqual(cli.execute(options, [selected]), 0)
        provenance = json.loads(options.provenance_file.read_text())["song"]
        self.assertEqual(provenance["source"], "discogs")
        self.assertEqual(provenance["value"], 4)
        self.assertFalse(provenance["pending"])

    def test_rejected_write_keeps_pending_source_and_does_not_create_update_lock(self):
        original = self.request
        def request(url, **kwargs):
            response = original(url, **kwargs)
            if urlparse(url).path.endswith("setRating"):
                response.json.return_value = {"subsonic-response": {"status": "failed", "error": {"code": 10}}}
            return response
        with patch.object(cli.requests, "get", side_effect=request), patch.object(cli, "DiscogsClient", return_value=self.provider):
            with self.assertRaises(RuntimeError):
                cli.main(["--provider", "discogs", "--unrated-only", "--album", "album", "--discogs-inherit-album-rating"])
        pending = json.loads(Path("logs/generated-ratings.json").read_text())["song"]
        self.assertTrue(pending["pending"])
        self.assertFalse(Path("logs/song_update_lock.json").exists())

    def test_personal_change_during_source_lookup_is_not_overwritten(self):
        match = self.provider.find_track.return_value
        def changed(*args, **kwargs):
            self.rating = 3
            return match
        self.provider.find_track.side_effect = changed
        self.assertEqual(self.sync("--album", "album", "--unrated-only", "--discogs-inherit-album-rating"), 0)
        self.assertEqual(self.writes, [])
        self.assertFalse(Path("logs/song_update_lock.json").exists())

    def test_release_versions_agree(self):
        self.assertEqual((self.previous / "VERSION").read_text().strip(), __version__)
        self.assertIn('version = "' + __version__ + '"', (self.previous / "pyproject.toml").read_text())


if __name__ == "__main__":
    unittest.main()
