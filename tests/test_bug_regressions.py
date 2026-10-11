import ast
from datetime import timedelta
import logging
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import Mock

import requests
from test_lastfm import load_functions


def definitions(names, context):
    # The standalone CLI starts a sync on import; execute only its definitions.
    tree = ast.parse(Path("sonicratings.py").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "sonicratings.py", "exec"), context)


class BugRegressionTests(unittest.TestCase):
    def config(self, **settings):
        context = dict(NAV_BASE_URL="https://server.invalid", NAV_USER="user", NAV_PASS="secret",
                       SPOTIFY_CLIENT_ID=None, SPOTIFY_CLIENT_SECRET=None, LASTFM_API_KEY=None,
                       TIDAL_CLIENT_ID=None, TIDAL_CLIENT_SECRET=None,
                       logging=Mock(), sys=sys, LIGHT_RED="", RESET="")
        context.update(settings)
        definitions({"validate_required_config"}, context)
        return context

    def test_missing_server_credentials_report_names_without_values(self):
        context = self.config(NAV_BASE_URL=None, NAV_USER="", NAV_PASS=None)
        with self.assertRaises(SystemExit) as error:
            context["validate_required_config"]("musicbrainz")
        self.assertEqual(error.exception.code, 1)
        message = context["logging"].error.call_args.args[0]
        for name in ("NAV_BASE_URL", "NAV_USER", "NAV_PASS"):
            self.assertIn(name, message)
        self.assertNotIn("secret", message)

    def test_only_selected_provider_credentials_are_required(self):
        context = self.config()
        context["validate_required_config"]("musicbrainz")
        for provider, names in (("spotify", ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")),
                                ("lastfm", ("LASTFM_API_KEY",)),
                                ("tidal", ("TIDAL_CLIENT_ID", "TIDAL_CLIENT_SECRET"))):
            with self.subTest(provider=provider), self.assertRaises(SystemExit):
                context["validate_required_config"](provider)
            message = context["logging"].error.call_args.args[0]
            for name in names:
                self.assertIn(name, message)
            complete = self.config(**{name: "secret" for name in names})
            complete["validate_required_config"](provider)

    def locks(self):
        context = dict(LOCK={}, BASE_LOCK_DURATION=7, LOCK_JITTER=24,
                       random=random, timedelta=timedelta, time=Mock(), save_lock=Mock())
        context["time"].time.return_value = 1000
        definitions({"get_lock_timestamp", "get_lock_expiry", "record_lock", "should_update"}, context)
        return context

    def test_saved_expiry_survives_repeated_checks_and_setting_changes(self):
        context = self.locks()
        context["record_lock"]("song", "Artist", "Album", "Song")
        expiry = context["LOCK"]["song"]["expires_at"]
        context.update(BASE_LOCK_DURATION=30, LOCK_JITTER=100)
        context["time"].time.return_value = expiry - 1
        self.assertEqual([context["should_update"]("song") for _ in range(100)], [False] * 100)
        context["time"].time.return_value = expiry + 1
        self.assertTrue(context["should_update"]("song"))

    def test_legacy_timestamps_use_stable_jitter_and_force_update_still_works(self):
        context = self.locks()
        expiry = context["get_lock_expiry"]("song", 1000)
        self.assertEqual([context["get_lock_expiry"]("song", 1000) for _ in range(100)], [expiry] * 100)
        for entry in (1000, {"timestamp": 1000}, {"updated_at": 1000}):
            context["LOCK"]["song"] = entry
            context["time"].time.return_value = 1000 + expiry - 1
            self.assertFalse(context["should_update"]("song"))
            context["time"].time.return_value = 1000 + expiry + 1
            self.assertTrue(context["should_update"]("song"))
        context["BASE_LOCK_DURATION"] = 0
        self.assertTrue(context["should_update"]("song"))
        self.assertTrue(context["should_update"]("new"))

    def test_unmatched_lastfm_tracks_preserve_ratings_and_remain_retryable(self):
        for existing in (0, 4):
            for preview in (False, True):
                with self.subTest(existing=existing, preview=preview):
                    response = Mock(status_code=200)
                    response.json.return_value = {"error": 6}
                    client = Mock(get=Mock(return_value=response), exceptions=requests.exceptions)
                    context = dict(logging=logging, requests=client,
                                   PROVIDER="lastfm", LASTFM_API_URL="https://example.invalid",
                                   LASTFM_API_KEY="fake", LASTFM_ARTIST_TOP_TRACKS={"Artist": {}},
                                   get_existing_rating=lambda _: existing, should_update=lambda _: True,
                                   UNRATED_ONLY=False, PREVIEW=preview, FOUND_AND_UPDATED=0,
                                   UNMATCHED_TRACKS=[], NOT_FOUND=0, TOTAL_TRACKS=0, SKIPPED_RATED=0,
                                   navidrome_get=Mock(), record_lock=Mock())
                    context.update({name: "" for name in ("LIGHT_RED", "LIGHT_BLUE", "RESET")})
                    load_functions(context)
                    context["process_track"]("local", "Artist", "Album", "Song")
                    context["navidrome_get"].assert_not_called()
                    context["record_lock"].assert_not_called()
                    self.assertEqual(context["NOT_FOUND"], 1)
                    self.assertEqual(context["UNMATCHED_TRACKS"], ["Artist - Album - Song"])


if __name__ == "__main__":
    unittest.main()
