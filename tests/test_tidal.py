import ast
import logging
import math
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import requests
from tidal_provider import TidalClient, popularity_score


def resource(kind, identity, **attributes):
    return {"type": kind, "id": identity, "attributes": attributes}


class TidalTests(unittest.TestCase):
    def test_scores(self):
        for value, expected in [(0, 0), (.2, 20), (.56, 56.00000000000001), (1, 100)]:
            self.assertAlmostEqual(popularity_score(resource("tracks", "1", popularity=value)), expected)
        for value in [None, "0.5", True, -1, 1.1, math.nan, math.inf]:
            self.assertIsNone(popularity_score(resource("tracks", "1", popularity=value)))

    def test_matching_rejects_cover_and_prefers_album(self):
        client = TidalClient("id", "secret")
        tracks = [resource("tracks", str(i), title="Song", popularity=.75) for i in range(3)]
        search = {"data": {"relationships": {"tracks": {"data": tracks}}}, "included": tracks}
        def response(path, **params):
            if path == "searchResults":
                return search
            identity = path.split("/")[-1]
            track = dict(tracks[int(identity)])
            track["relationships"] = {"artists": {"data": [{"type": "artists", "id": "a"}]},
                                      "albums": {"data": [{"type": "albums", "id": "b"}]}}
            return {"data": track, "included": [
                resource("artists", "a", name="Cover Artist" if identity == "0" else "Artist"),
                resource("albums", "b", title="Album" if identity == "2" else "Compilation")]}
        client.get = Mock(side_effect=response)
        self.assertEqual(client.find_track("Artist", "Song", "Album")["id"], "2")
        self.assertIsNone(client.find_track("Artist", "Song (Live)", "Album"))

    @patch("tidal_provider.requests.request")
    def test_authentication_refresh(self, request):
        token = Mock(status_code=200)
        token.json.return_value = {"access_token": "token", "expires_in": 3600}
        unauthorized = Mock(status_code=401)
        unauthorized.raise_for_status.side_effect = requests.HTTPError(response=unauthorized)
        success = Mock(status_code=200)
        success.json.return_value = {"data": []}
        request.side_effect = [token, unauthorized, token, success]
        self.assertEqual(TidalClient("id", "secret").get("tracks"), {"data": []})
        self.assertEqual(request.call_count, 4)
        self.assertEqual(request.call_args.kwargs["params"]["countryCode"], "US")

    @patch("tidal_provider.time.sleep")
    @patch("tidal_provider.requests.request")
    def test_rate_limit_retry(self, request, sleep):
        limited = Mock(status_code=429, headers={"Retry-After": "2"})
        success = Mock(status_code=200)
        success.json.return_value = {"data": []}
        request.side_effect = [limited, success]
        self.assertEqual(TidalClient("id", "secret")._request("GET", "url"), {"data": []})
        sleep.assert_called_once_with(2)

    def test_navidrome_writes_and_preview(self):
        # Load function definitions only: importing the CLI would authenticate and run a sync.
        tree = ast.parse(Path("sonicratings.py").read_text())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in ("get_rating_from_popularity", "process_track")]
        for score, preview, expected in [(None, 0, None), (math.nan, 0, None), (.1, 0, None), (.56, 1, None), (.56, 0, 3)]:
            with self.subTest(score=score, preview=preview):
                client = Mock()
                client.find_track.return_value = (None if score is None else
                    resource("tracks", "1", title="Song", popularity=score))
                write, lock = Mock(), Mock()
                context = dict(logging=logging, requests=requests, math=math, re=__import__("re"),
                    PROVIDER="tidal", tidal_client=client, popularity_score=popularity_score,
                    get_existing_rating=lambda _: 0, should_update=lambda _: True,
                    UNRATED_ONLY=True, PREVIEW=preview, FOUND_AND_UPDATED=0,
                    UNMATCHED_TRACKS=[], NOT_FOUND=0, TOTAL_TRACKS=0, SKIPPED_RATED=0,
                    NAV_BASE_URL="http://nav", NAV_USER="user", HEX_ENCODED_PASS="pass",
                    navidrome_get=write, record_lock=lock)
                context.update({name: "" for name in ["LIGHT_YELLOW", "RESET", "LIGHT_CYAN", "LIGHT_BLUE", "LIGHT_GREEN", "LIGHT_RED"]})
                exec(compile(ast.Module(body=functions, type_ignores=[]), "sonicratings.py", "exec"), context)
                context["process_track"]("local", "Artist", "Album", "Song")
                if expected is None:
                    write.assert_not_called()
                    lock.assert_not_called()
                else:
                    self.assertIn(f"rating={expected}", write.call_args.args[0])
                    lock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
