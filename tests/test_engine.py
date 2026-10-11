import io
import json
import unittest
from unittest.mock import patch
from sonicratings_engine import cli
from sonicratings_engine.ratings import RatingProvider, score_lastfm


class EngineTests(unittest.TestCase):
    def test_scoring_api_and_cli_share_results(self):
        expected = score_lastfm(1000000, 10000000, 1)
        with patch("sys.argv", ["sonicratings-score", "--listeners", "1000000", "--plays", "10000000", "--rank", "1"]), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(cli.main(), 0)
            self.assertEqual(json.loads(output.getvalue()), {"rating": expected, "source": "lastfm"})

    def test_absent_key_selects_musicbrainz_and_preserves_source(self):
        class MB:
            def request(self, endpoint, **params):
                self.endpoint = endpoint
                return {"rating": {"value": 3.8}}
        mb = MB()
        result = RatingProvider(mb).rating({"recording": "00000000-0000-4000-8000-000000000001"})
        self.assertEqual(result, (4, "musicbrainz"))
        self.assertTrue(mb.endpoint.startswith("recording/"))


if __name__ == "__main__":
    unittest.main()
