import io
import json
import unittest
from unittest.mock import patch
from sonicratings import score as cli
from sonicratings.score import score_lastfm


class ScoringTests(unittest.TestCase):
    def test_scoring_api_and_cli_share_results(self):
        expected = score_lastfm(1000000, 10000000, 1)
        with patch("sys.argv", ["sonicratings-score", "--listeners", "1000000", "--plays", "10000000", "--rank", "1"]), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(cli.main(), 0)
            self.assertEqual(json.loads(output.getvalue()), {"rating": expected, "source": "lastfm"})

    def test_scoring_stays_selective_for_high_stars(self):
        self.assertEqual(score_lastfm(1000000, 10000000, 1), 5)
        self.assertLessEqual(score_lastfm(1000, 2000, 100), 3)
        self.assertEqual(score_lastfm(0, 0, None), 0)


if __name__ == "__main__":
    unittest.main()
