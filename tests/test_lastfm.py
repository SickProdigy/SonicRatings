import ast
import logging
import math
from pathlib import Path
import re
import unittest
from unittest.mock import Mock
from sonicratings.lastfm_matching import lookup_variants, matches_track, normalize_title


def load_functions(context):
    # Load isolated definitions with the fake runtime context used by these regressions.
    tree = ast.parse(Path("sonicratings/cli.py").read_text(encoding="utf-8"))
    names = {"get_rating_from_popularity", "get_lastfm_popularity", "get_lastfm_rating", "process_track", "process_album"}
    context.update(lookup_variants=lookup_variants, matches_track=matches_track, normalize_title=normalize_title)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "sonicratings/cli.py", "exec"), context)


class LastfmTests(unittest.TestCase):
    def test_spelling_variants_preserve_versions(self):
        self.assertIn(("$NOT", "LOCKED IN"), lookup_variants("$NOT", "LOCKED + IN"))
        self.assertIn(("G-Eazy", "Dont Go"), lookup_variants("G\u2010Eazy", "Don\u2019t Go"))
        self.assertEqual(normalize_title("\u200eDon't Go"), normalize_title("Dont Go"))
        for title in ["Song (Alice remix)", "Song [Live]", "Song (instrumental)",
                      "Song (radio edit)", "Song (2020 remastered)"]:
            variants = lookup_variants("Artist", title)
            for artist, candidate in variants:
                with self.subTest(title=title, candidate=candidate):
                    self.assertNotEqual(normalize_title(candidate), "song")
                    self.assertFalse(matches_track({"name": "Song"}, artist, candidate))
        self.assertFalse(matches_track({"name": "Song (Bob remix)"}, "Artist", "Song (Alice remix)"))
        self.assertFalse(matches_track({"name": "Song", "artist": {"name": "Cover Artist"}}, "Artist", "Song"))

    def test_compilation_uses_track_artist_for_lastfm(self):
        response = Mock()
        response.json.return_value = {"subsonic-response": {"album": {"artist": "Various Artists",
            "song": [{"id": "1", "artist": "Actual Artist", "album": "Compilation", "title": "Song"}]}}}
        context = dict(PROVIDER="lastfm", SHOULD_DELAY=False, NAV_BASE_URL="https://example.invalid",
            NAV_USER="test", HEX_ENCODED_PASS="test", navidrome_get=Mock(return_value=response))
        load_functions(context)
        context["process_track"] = Mock()
        context["process_album"]("album")
        context["process_track"].assert_called_once_with("1", "Actual Artist", "Compilation", "Song")

    def test_cutoffs_and_five_star_requirements(self):
        context = {}
        load_functions(context)
        cases = [(16, 1, 100000, 0), (17, 1, 100000, 1),
                 (33, 1, 100000, 1), (34, 1, 100000, 2),
                 (49, 1, 100000, 2), (50, 1, 100000, 3),
                 (64, 1, 100000, 3), (65, None, 100000, 4),
                 (79, 1, 100000, 4), (80, 3, 100000, 5),
                 (80, 4, 100000, 4), (80, None, 100000, 4),
                 (80, 0, 100000, 4), (80, 1, 99999, 4),
                 (100, None, 1000000, 4)]
        for score, rank, listeners, expected in cases:
            with self.subTest(score=score, rank=rank, listeners=listeners):
                self.assertEqual(context["get_lastfm_rating"](score, rank, listeners), expected)

    def test_sync_uses_lastfm_cutoffs_and_respects_preview_and_existing_ratings(self):
        for listeners, preview, existing, expected in [(712598, 0, 0, 5),
                (712598, 1, 0, None), (712598, 0, 2, None), (10000, 0, 0, 4)]:
            with self.subTest(listeners=listeners, preview=preview, existing=existing):
                response = Mock()
                response.json.return_value = {"track": {"name": "Song", "listeners": str(listeners),
                                                        "playcount": str(listeners * 10)}}
                write, lock = Mock(), Mock()
                context = dict(logging=logging, math=math, re=re, requests=Mock(get=Mock(return_value=response)),
                    PROVIDER="lastfm", LASTFM_API_URL="https://example.invalid", LASTFM_API_KEY="test",
                    LASTFM_ARTIST_TOP_TRACKS={"Artist": {"song": {"rank": 1, "name": "Song",
                        "listeners": listeners, "playcount": listeners * 10}}},
                    get_existing_rating=lambda _: existing, should_update=lambda _: True,
                    UNRATED_ONLY=True, PREVIEW=preview, FOUND_AND_UPDATED=0,
                    UNMATCHED_TRACKS=[], NOT_FOUND=0, TOTAL_TRACKS=0, SKIPPED_RATED=0,
                    NAV_BASE_URL="https://example.invalid", NAV_USER="test", HEX_ENCODED_PASS="test",
                    navidrome_get=write, record_lock=lock)
                context.update({name: "" for name in ["LIGHT_YELLOW", "RESET", "LIGHT_CYAN",
                    "LIGHT_BLUE", "LIGHT_GREEN", "LIGHT_RED"]})
                load_functions(context)
                context["process_track"]("local", "Artist", "Album", "Song")
                if expected is None:
                    write.assert_not_called()
                    lock.assert_not_called()
                else:
                    write.assert_called_once()
                    self.assertIn(f"rating={expected}", write.call_args.args[0])
                    lock.assert_called_once()

    def test_missing_spelling_and_empty_entry_fall_back_to_populated_variant(self):
        # The original lookup returns an empty entry, then the space-only spelling succeeds.
        def get_response(*args, **kwargs):
            title = kwargs["params"]["track"]
            response = Mock()
            response.json.return_value = {"track": {"name": title, "listeners": "0", "playcount": "0"}}
            if title == "LOCKED IN":
                response.json.return_value = {"track": {"name": title, "artist": {"name": "$NOT"},
                    "listeners": "10000", "playcount": "100000"}}
            return response
        write = Mock()
        context = dict(logging=logging, math=math, re=re, requests=Mock(get=Mock(side_effect=get_response)),
            PROVIDER="lastfm", LASTFM_API_URL="https://example.invalid", LASTFM_API_KEY="test",
            LASTFM_ARTIST_TOP_TRACKS={"$NOT": {"locked in": {"rank": 1, "name": "LOCKED IN",
                "listeners": 10000, "playcount": 100000}}},
            get_existing_rating=lambda _: 0, should_update=lambda _: True,
            UNRATED_ONLY=True, PREVIEW=0, FOUND_AND_UPDATED=0,
            UNMATCHED_TRACKS=[], NOT_FOUND=0, TOTAL_TRACKS=0, SKIPPED_RATED=0,
            NAV_BASE_URL="https://example.invalid", NAV_USER="test", HEX_ENCODED_PASS="test",
            navidrome_get=write, record_lock=Mock())
        context.update({name: "" for name in ["LIGHT_YELLOW", "RESET", "LIGHT_CYAN",
            "LIGHT_BLUE", "LIGHT_GREEN", "LIGHT_RED"]})
        load_functions(context)
        context["process_track"]("local", "$NOT", "Album", "LOCKED + IN")
        write.assert_called_once()
        self.assertIn("rating=4", write.call_args.args[0])

        # Catalog counts also rescue tracks when every track.getInfo variant is missing.
        write.reset_mock()
        missing = Mock()
        missing.json.return_value = {"error": 6, "message": "Track not found"}
        context["requests"].get.side_effect = None
        context["requests"].get.return_value = missing
        context["process_track"]("another", "$NOT", "Album", "LOCKED + IN")
        write.assert_called_once()
        self.assertIn("rating=4", write.call_args.args[0])
