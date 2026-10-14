import ast
import argparse
import io
import logging
import math
import re
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import requests
from sonicratings.discogs import DiscogsClient, DiscogsError, positive_id, release_rating


def release(identity=10, **changes):
    result = {"id": identity, "title": "Album", "artists": [{"name": "Artist (2)"}],
              "master_id": 1, "community": {"rating": {"average": 3.87, "count": 20}},
              "tracklist": [{"type_": "track", "title": "Song"}]}
    result.update(changes)
    return result


class DiscogsTests(unittest.TestCase):
    def test_native_rating_validation_and_rounding(self):
        for average, expected in [(1, 1), (2.49, 2), (2.5, 3), (3.87, 4), (5, 5)]:
            self.assertEqual(release_rating(release(community={"rating": {
                "average": average, "count": 5}}))["rating"], expected)
        for average in [None, "3.87", True, 0, -1, 5.01, math.nan, math.inf]:
            self.assertIsNone(release_rating(release(community={"rating": {
                "average": average, "count": 20}})))
        for count in [None, "20", True, 0, -1, 4]:
            self.assertIsNone(release_rating(release(community={"rating": {
                "average": 4, "count": count}})))
        self.assertIsNone(release_rating(release(community=None)))
        self.assertIsNone(release_rating(release(), min_votes=21))

    def client(self, data=None):
        client = DiscogsClient()
        client._get = Mock(return_value=data or release())
        return client

    def test_explicit_edition_still_checks_artist_album_and_track_version(self):
        client = self.client()
        matched = client.find_track("Artist", "Song", "Album", release_id=10)
        self.assertEqual((matched["rating"], matched["source"], matched["selection"]),
                         (4, "discogs-release", "explicit edition"))
        for artist, album, title in [("Cover Artist", "Album", "Song"),
                                      ("Artist", "Other Album", "Song"),
                                      ("Artist", "Album", "Song (Live)"),
                                      ("Artist", "Album", "Song (Remix)")]:
            self.assertIsNone(client.find_track(artist, title, album, release_id=10))

    def test_main_release_selection_and_album_cache(self):
        client = DiscogsClient()
        master = {"title": "Album", "artists": [{"name": "Artist"}], "main_release": 10}
        data = {"database/search": {"results": [{"type": "master", "id": 1}]},
                "masters/1": master, "releases/10": release()}
        client._get = Mock(side_effect=lambda path, **_: data[path])
        match = client.find_track("Artist", "Song", "Album")
        self.assertEqual(match["selection"], "master main release")
        self.assertEqual(match["release_id"], 10)
        self.assertEqual(client._get.call_count, 3)
        client.find_track("Artist", "Song", "Album")
        self.assertEqual(client._get.call_count, 3)

    def test_ambiguous_and_truncated_searches_are_not_selected(self):
        for results, pages in [([{"type": "master", "id": 1}, {"type": "master", "id": 2}], 1),
                               ([{"type": "master", "id": 1}], 2),
                               ([{"type": "master", "id": i} for i in range(1, 7)], 1)]:
            client = DiscogsClient()
            def get(path, **_):
                if path == "database/search":
                    return {"results": results, "pagination": {"pages": pages}}
                return {"title": "Album", "artists": [{"name": "Artist"}], "main_release": 10}
            client._get = Mock(side_effect=get)
            self.assertIsNone(client.find_track("Artist", "Song", "Album"))
            self.assertFalse(any(c.args[0].startswith("releases/") for c in client._get.call_args_list))

    def test_unique_release_fallback_and_ambiguous_editions(self):
        for count in [1, 2]:
            client = DiscogsClient()
            def get(path, **params):
                if path == "database/search":
                    return {"results": [] if params["type"] == "master" else [
                        {"type": "release", "id": i} for i in range(10, 10 + count)]}
                return release(int(path.split("/")[-1]))
            client._get = Mock(side_effect=get)
            result = client.find_track("Artist", "Song", "Album")
            if count == 1:
                self.assertEqual(result["selection"], "unique release")
            else:
                self.assertIsNone(result)

    def test_wrong_main_release_is_rejected(self):
        client = DiscogsClient()
        client._search = Mock(return_value={1: {"main_release": 10}})
        client._get = Mock(return_value=release(master_id=2))
        self.assertIsNone(client.find_track("Artist", "Song", "Album"))

    def test_compilation_performers_and_nested_tracklists(self):
        client = self.client(release(artists=[{"name": "Various"}], tracklist=[
            {"type_": "heading", "title": "Song"},
            {"type_": "index", "title": "Suite", "sub_tracks": [
                {"title": "Song", "artists": [{"name": "Performer"}]}]}]))
        self.assertIsNotNone(client.find_track("Performer", "Song", "Album",
            album_artist="Various Artists", release_id=10))
        self.assertIsNone(client.find_track("Other Performer", "Song", "Album",
            album_artist="Various Artists", release_id=10))

    def test_low_vote_and_missing_rating_results_are_cached(self):
        client = self.client(release(community={"rating": {"average": 5, "count": 1}}))
        for _ in range(2):
            self.assertIsNone(client.find_track("Artist", "Song", "Album", release_id=10))
        client._get.assert_called_once()

    def test_ids_and_vote_threshold_validation(self):
        for value in [0, -1, True, "abc", "1/other", "01"]:
            with self.assertRaises(ValueError):
                self.client().find_release("Artist", "Album", value)
        for value in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError):
                DiscogsClient(min_votes=value)

    def test_cli_requires_explicit_inheritance_and_valid_overrides(self):
        from sonicratings.cli import parse_args
        for args, accepted in [(["--provider", "discogs"], False),
                (["--provider", "discogs", "--preview"], True),
                (["--provider", "discogs", "--discogs-inherit-album-rating"], True),
                (["--provider", "discogs", "--preview", "--discogs-release", "local=10"], True),
                (["--provider", "discogs", "--preview", "--discogs-release", "local=0"], False),
                (["--provider", "discogs", "--preview", "--discogs-release", "local=10",
                  "--discogs-release", "local=11"], False),
                (["--provider", "discogs", "--preview", "--discogs-min-votes", "0"], False),
                (["--provider", "lastfm", "--discogs-inherit-album-rating"], False)]:
            with self.subTest(args=args), patch("sys.argv", ["sonicratings/cli.py", *args]), patch("sys.stderr", new_callable=io.StringIO):
                context = {"argparse": argparse, "positive_id": positive_id, "__version__": "test"}
                if accepted:
                    parse_args(args)
                else:
                    with self.assertRaises(SystemExit) as error:
                        parse_args(args)
                    self.assertEqual(error.exception.code, 2)

    def test_album_passes_compilation_artist_and_edition_override(self):
        tree = ast.parse(Path("sonicratings/cli.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "process_album")
        response = Mock()
        response.json.return_value = {"subsonic-response": {"album": {
            "artist": "Various Artists", "song": [{"id": "song", "artist": "Performer",
                "album": "Compilation", "title": "Song"}]}}}
        process = Mock()
        context = {"SHOULD_DELAY": False, "NAV_BASE_URL": "http://nav", "NAV_USER": "user",
                   "HEX_ENCODED_PASS": "pass", "navidrome_get": Mock(return_value=response),
                   "requests": requests, "logging": logging, "PROVIDER": "discogs",
                   "DISCOGS_RELEASE_OVERRIDES": {"local": 10}, "process_track": process}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "sonicratings/cli.py", "exec"), context)
        context["process_album"]("local")
        process.assert_called_once_with("song", "Performer", "Compilation", "Song",
            discogs_album_artist="Various Artists", discogs_release_id=10)

    @patch("sonicratings.discogs.time.sleep")
    def test_rate_limits_retries_cache_and_secret_handling(self, sleep):
        session = Mock()
        limited = Mock(status_code=429, headers={"Retry-After": "60"})
        success = Mock(status_code=200, ok=True, headers={"X-Discogs-Ratelimit": "25"})
        success.json.return_value = release()
        session.get.side_effect = [limited, success]
        client = DiscogsClient("secret-token", session=session)
        self.assertEqual(client._get("releases/10"), release())
        self.assertEqual(client._get("releases/10"), release())
        self.assertEqual(session.get.call_count, 2)
        self.assertGreaterEqual(sleep.call_args.args[0], 59)
        self.assertAlmostEqual(client.interval, 2.45)
        self.assertNotIn("secret-token", session.get.call_args.args[0])
        self.assertEqual(session.get.call_args.kwargs["headers"]["Authorization"], "Discogs token=secret-token")

    @patch("sonicratings.discogs.time.sleep")
    def test_provider_failures_are_not_cached_as_misses(self, sleep):
        for code in [401, 403, 429, 500]:
            session = Mock()
            session.get.return_value = Mock(status_code=code, ok=False, headers={})
            client = DiscogsClient(session=session)
            with self.assertRaises(DiscogsError):
                client.find_track("Artist", "Song", "Album", release_id=10)
            self.assertEqual(client.albums, {})
            self.assertEqual(client.resources, {})

    @patch("sonicratings.discogs.time.sleep")
    def test_missing_release_and_invalid_json(self, sleep):
        session = Mock()
        session.get.return_value = Mock(status_code=404, headers={})
        client = DiscogsClient(session=session)
        self.assertIsNone(client.find_release("Artist", "Album", 10))
        session.get.return_value = Mock(status_code=200, ok=True, headers={})
        session.get.return_value.json.side_effect = ValueError("bad JSON")
        with self.assertRaises(DiscogsError):
            client.find_release("Artist", "Album", 11)

    def test_preview_writes_skips_and_failure_preservation(self):
        tree = ast.parse(Path("sonicratings/cli.py").read_text(encoding="utf-8"))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in ("get_rating_from_popularity", "process_track")]
        match = {"average": 3.87, "rating": 4, "matched_title": "Song",
                 "release_id": 10, "votes": 20, "selection": "explicit edition"}
        for preview, existing, locked, result in [(True, 0, False, match),
                (False, 0, False, match), (False, 3, False, match),
                (False, 0, True, match), (False, 0, False, None),
                (False, 0, False, DiscogsError("failed")), (False, None, False, match)]:
            with self.subTest(preview=preview, existing=existing, locked=locked, result=result):
                client, write, lock = Mock(), Mock(), Mock()
                if isinstance(result, Exception):
                    client.find_track.side_effect = result
                else:
                    client.find_track.return_value = result
                context = dict(logging=logging, requests=requests, math=math, re=re,
                    PROVIDER="discogs", discogs_client=client, DiscogsError=DiscogsError,
                    get_existing_rating=lambda _: existing, should_update=lambda _: not locked,
                    UNRATED_ONLY=True, PREVIEW=preview, FOUND_AND_UPDATED=0,
                    UNMATCHED_TRACKS=[], NOT_FOUND=0, TOTAL_TRACKS=0, SKIPPED_RATED=0,
                    NAV_BASE_URL="http://nav", NAV_USER="user", HEX_ENCODED_PASS="pass",
                    navidrome_get=write, record_lock=lock)
                context.update({name: "" for name in ["LIGHT_YELLOW", "RESET", "LIGHT_CYAN", "LIGHT_BLUE", "LIGHT_GREEN", "LIGHT_RED"]})
                exec(compile(ast.Module(body=functions, type_ignores=[]), "sonicratings/cli.py", "exec"), context)
                if isinstance(result, Exception) or existing is None:
                    with self.assertRaises(DiscogsError):
                        context["process_track"]("local", "Artist", "Album", "Song")
                else:
                    context["process_track"]("local", "Artist", "Album", "Song")
                if not preview and existing == 0 and not locked and isinstance(result, dict):
                    self.assertIn("rating=4", write.call_args.args[0])
                    lock.assert_called_once()
                else:
                    write.assert_not_called()
                    lock.assert_not_called()
                if existing or existing is None or locked:
                    client.find_track.assert_not_called()


if __name__ == "__main__":
    unittest.main()
