"""Small CLI around the same scoring API available to a future GUI."""
import argparse
import json
from .ratings import score_lastfm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listeners", required=True, type=int)
    parser.add_argument("--plays", required=True, type=int)
    parser.add_argument("--rank", type=int)
    args = parser.parse_args()
    if args.listeners < 0 or args.plays < 0 or (args.rank is not None and args.rank < 1):
        parser.error("Counts must be nonnegative and rank must be positive")
    print(json.dumps({"rating": score_lastfm(args.listeners, args.plays, args.rank), "source": "lastfm"}))
    return 0
