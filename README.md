# SonicRatings

Bring track popularity and community ratings into your Navidrome or Subsonic-compatible music library. SonicRatings supports Spotify, TIDAL, Last.fm, and MusicBrainz as rating sources.

Originally called **SPTNR** (Spotify Popularity to Navidrome Ratings), this script was developed to repurpose the star ratings in Navidrome. As a Navidrome user who utilizes the 'favorite' feature instead of star ratings, I wanted to give new life and utility to the unused rating system. By mapping provider scores to library ratings, SonicRatings provides a quick way to identify popular tracks. This becomes particularly useful when frequently adding new albums and artists, especially those you're not familiar with.

The CLI is `sonicratings.py`, the automation package is `sonicratings-engine`, and the Compose service is `sonicratings`. Build the local Docker image below; a prebuilt SonicRatings image has not been published yet.

![Screenshot of script and phone](https://i.imgur.com/7NhSQFM.png)

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Quick Start](#quick-start)
4. [Using Docker Compose](#using-docker-compose)
5. [Running Natively or Building Locally](#running-natively-or-building-locally)
6. [Usage](#usage)
7. [Examples](#examples)
8. [Resuming Interrupted Sessions](#resuming-interrupted-sessions)
9. [Managing Docker Containers](#managing-docker-containers)
10. [Mapping Provider Scores to Library Ratings](#mapping-provider-scores-to-library-ratings)
11. [Estimated Processing Times](#estimated-processing-times)
12. [Importance of Accurate Metadata for Track Lookup](#importance-of-accurate-metadata-for-track-lookup)
13. [Logs](#logs)
14. [Installable Automation Engine](#installable-automation-engine)

## Features

- **Spotify Integration**: Connects to Spotify's API to fetch popularity data for tracks.
- **TIDAL Support**: Uses TIDAL catalog popularity with the same star conversion as Spotify. Requires TIDAL developer app credentials, not Spotify credentials.
- **Last.fm Support**: Can use Last.fm artist top-track position, listeners, and playcounts as an alternate popularity source. (A useful alternative when you want broader catalog coverage.)
- **MusicBrainz Support**: Can use MusicBrainz community ratings as a rating source. (Currently not a lot of ratings available, but worth having as an option for the future.)
- **Subsonic/Navidrome Integration**: Updates personal track ratings through the Subsonic API based on provider scores.
- **Flexible Processing**: Process specific artists, albums, or a range of artists or albums.
- **Unrated-Only Mode**: Skip tracks that already have a rating and only update unrated songs.
- **Preview Mode**: Run the script in preview mode to see changes without making any actual updates.
- **Logging**: Detailed logging of the process, both in the console and to a file.
- **Docker Support**: Run the script in a Docker container for consistent environments and ease of use.

## Requirements

- Python 3.x or Docker
- Access to a Navidrome or compatible Subsonic server
- Optional: A Spotify Developer account with an API key ([Get your Spotify API key here](https://developer.spotify.com/dashboard/create))
- Optional: a Last.fm API key if you want to use Last.fm as the popularity provider
- Optional: TIDAL developer app credentials if you want to use TIDAL
- MusicBrainz community rating lookups do not require provider credentials

**Compatibility Note**: SonicRatings is designed for Navidrome and uses the Subsonic API. It should work with any Subsonic/Navidrome server supporting the required browsing, personal-rating, and authentication APIs. Other server implementations have not been tested live. If you successfully use it with another server, please open an issue so I can document compatibility and assist others.

## Quick Start

Build SonicRatings from this checkout, then replace the environment variable values below with your own:

```console
docker build -t sonicratings:local .
```

```console
docker run -t \
  -e NAV_BASE_URL=your_navidrome_server_url \
  -e NAV_USER=your_navidrome_username \
  -e NAV_PASS=your_navidrome_password \
  -e SPOTIFY_CLIENT_ID=your_spotify_client_id \
  -e SPOTIFY_CLIENT_SECRET=your_spotify_client_secret \
  sonicratings:local
```

If you want to use Last.fm instead of Spotify, add `-e LASTFM_API_KEY=your_lastfm_api_key` and run with `--provider lastfm`.

**Note**: The `-t` flag is used to allocate a pseudo-terminal which assists in displaying colored and bold text in the terminal output, which this script uses.

### Using Docker Compose

1. **Create `docker-compose.yml` File**: Set up your `docker-compose.yml` file with the following content, replacing the environment variables with your own details:

   ```yaml
   version: "3.8"

   services:
     sonicratings:
       container_name: sonicratings
       build: .
       image: sonicratings:local
       environment:
         - NAV_BASE_URL=your_navidrome_server_url
         - NAV_USER=your_navidrome_username
         - NAV_PASS=your_navidrome_password
         - SPOTIFY_CLIENT_ID=your_spotify_client_id
         - SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
       volumes:
         - ./logs:/usr/src/app/logs
   ```

2. **Run the Script**: Execute the Docker Compose command to run the script:

   ```console
   docker-compose run sonicratings
   ```

## Running Natively or Building Locally

For those who prefer running the script natively using Python or building the Docker image locally, the following steps apply:

### Running Natively (Without Docker)

1. **Clone the Repository**: Clone the full repository to your local machine; `sonicratings.py` also imports the matching and provider modules in this checkout.

2. **Install Python Packages**: Use the `requirements.txt` file to install dependencies:

   ```console
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**: Rename `.env.example` to `.env` and fill in your details:

   ```console
   mv .env.example .env
   # Edit the .env file with your details
   ```

4. **Run the Script**: Execute the script with Python:

   ```console
   python sonicratings.py [options]
   ```

### Building and Running with Docker Locally

1. **Clone the Repository**: Clone the full repository to your local machine so the local Docker build includes the matching and provider modules.

2. **Configure Docker Compose**: Rename and edit your `docker-compose.yml`:

   ```console
   mv docker-compose.yml.example docker-compose.yml
   # Edit the docker-compose.yml file
   ```

3. **Check the Docker Image Source**: The example uses `build: .` and the local image tag `sonicratings:local`.

4. **Build and Run**: Build the Docker image and run the script:

   ```console
   docker-compose build
   docker-compose run sonicratings [options]
   ```

## Usage

The script supports various options for flexible usage. Below are examples of how to run the script with different options, using Python, Docker Compose, and Docker Run methods. Replace `[options]` with any of the specified options based on your needs.

### Options

- `-p, --preview`: Execute the script in preview mode (no changes made).
- `-a, --artist ARTIST_ID`: Process a specific artist. Multiple artists can be specified.
- `-b, --album ALBUM_ID`: Process a specific album. Multiple albums can be specified.
- `-s, --start START_INDEX`: Start processing from the artist at the specified index (0-based).
- `-l, --limit LIMIT`: Limit the processing to a specific number of artists from the start index.
- `-d, --lock-duration DURATION`: Number of days to lock song updates (0 to force update every time).
- `--navidrome-retries RETRIES`: Number of attempts for Navidrome API requests. Defaults to 3.
- `--navidrome-timeout SECONDS`: Base timeout for Navidrome API requests. Defaults to 10 seconds and increases on each retry.
- `--provider spotify|lastfm|musicbrainz|tidal`: Choose the source used to derive the rating. Spotify is the default.
- `--unrated-only`: Only update songs that do not already have a Navidrome rating.

### Command Formats

1. **Running Natively (Python)**:

   ```console
   python sonicratings.py [options]
   ```

2. **Using Docker Compose**:

   ```console
   docker-compose run sonicratings [options]
   ```

3. **Using Docker Run**:
   ```console
   docker run -t [environment variables] sonicratings:local [options]
   ```

## Examples

- **Preview Mode**:
  Run the script in preview mode to see changes without making any actual updates.

  - Python: `python sonicratings.py -p`
  - Docker Compose: `docker-compose run sonicratings -p`
  - Docker Run: `docker run -t [env vars] sonicratings:local -p`

- **Process Specific Artist**:
  Process only one artist by specifying their ID.

  - Python: `python sonicratings.py -a artist_id`
  - Docker Compose: `docker-compose run sonicratings -a artist_id`
  - Docker Run: `docker run -t [env vars] sonicratings:local -a artist_id`

- **Process Specific Albums**:
  Process multiple specific albums by specifying their IDs.

  - Python: `python sonicratings.py -b album_id1 -b album_id2`
  - Docker Compose: `docker-compose run sonicratings -b album_id1 -b album_id2`
  - Docker Run: `docker run -t [env vars] sonicratings:local -b album_id1 -b album_id2`

- **Process Range of Artists**:
  Process artists starting from a certain index with a limit.
  - Python: `python sonicratings.py -s 10 -l 5`
  - Docker Compose: `docker-compose run sonicratings -s 10 -l 5`
  - Docker Run: `docker run -t [env vars] sonicratings:local -s 10 -l 5`

- **Only Update Unrated Songs**:
   Skip tracks that already have a rating in Navidrome.
   - Python: `python sonicratings.py --unrated-only`
   - Docker Compose: `docker-compose run sonicratings --unrated-only`
   - Docker Run: `docker run -t [env vars] sonicratings:local --unrated-only`

- **Tolerate Slow Navidrome Scans**:
   Retry Navidrome API calls and increase the timeout for each retry.
   - Python: `python sonicratings.py --navidrome-retries 3 --navidrome-timeout 10`
   - Docker Compose: `docker-compose run sonicratings --navidrome-retries 3 --navidrome-timeout 10`
   - Docker Run: `docker run -t [env vars] sonicratings:local --navidrome-retries 3 --navidrome-timeout 10`

- **Use Last.fm as the Provider**:
   Use Last.fm artist top-track position, listener, and playcount data instead of Spotify popularity.
   - Python: `LASTFM_API_KEY=... python sonicratings.py --provider lastfm`
   - Docker Compose: `docker-compose run -e LASTFM_API_KEY=... sonicratings --provider lastfm`
   - Docker Run: `docker run -t -e LASTFM_API_KEY=... [env vars] sonicratings:local --provider lastfm`

   Last.fm does not provide a Spotify-style popularity number, so the script derives one from three signals:

   - **Artist top-track position**: where the track appears in Last.fm's `artist.getTopTracks` results for that artist. This is the largest part of the score.
   - **Listener reach**: the track's unique Last.fm listener count, scaled logarithmically.
   - **Replay engagement**: plays per listener, used as a small capped bonus.

   This keeps ordinary catalog tracks mostly in the 2-3 star range while letting occasional artist standouts reach 4-5 stars.

   Last.fm lookups try deduplicated spelling variants for Unicode apostrophes/dashes,
   invisible characters, punctuation, and spaced `+` separators. Empty catalog entries
   do not prevent trying another spelling. Remix, live, instrumental, and other version
   descriptors are retained, and returned titles/artists are checked before scoring.
   Compilation lookups use each song's artist rather than `Various Artists`. Artist
   top-track matching uses the same punctuation normalization as track lookup.
   If `track.getInfo` misses a track, a matching entry in that artist's top-track
   catalog can supply listener/play counts; the same title/version checks apply.

- **Use MusicBrainz as the Provider**:
   Use MusicBrainz ratings to derive the same 0-5 Navidrome rating.
   - Python: `python sonicratings.py --provider musicbrainz`
   - Docker Compose: `docker-compose run sonicratings --provider musicbrainz`
   - Docker Run: `docker run -t [env vars] sonicratings:local --provider musicbrainz`

### Use TIDAL as the Provider

Create an app in the [TIDAL developer portal](https://developer.tidal.com/) and set `TIDAL_CLIENT_ID` and `TIDAL_CLIENT_SECRET` in `.env` or your Compose environment. Set `TIDAL_COUNTRY_CODE` to your two-letter catalog country (default: `US`). Catalog lookup uses the client credentials flow; your personal TIDAL login and Spotify credentials are not required.

Preview before applying:

```console
python sonicratings.py --provider tidal --unrated-only --preview
```

For the local Docker build:

```console
docker compose build sonicratings
docker compose run --rm sonicratings --provider tidal --unrated-only --preview
```

Remove `--preview` to apply ratings. Searches require matching artist and title (including version), preferring matching albums. Missing matches or missing/invalid popularity preserve existing ratings. Scores mapping to zero do not write a rating or an update lock, so unrated tracks remain eligible on later runs, subject to any existing lock. API failures stop the run rather than clearing ratings.

## Resuming Interrupted Sessions

In cases where your session gets interrupted - for instance, if your machine goes to sleep, you encounter rate limits from Spotify, or for any other reason that causes the script to not complete - you have the option to resume from where you left off.

To determine the point of interruption, check the log file. The log entry will contain details of the artist it failed on, along with the index in a format similar to: `Artist: ARTIST_NAME (ARTIST_NAVIDROME_ID)[INDEX]`. Here, the index is enclosed in brackets.

When you restart the script, use the `-s INDEX` option, where `INDEX` is the index number from the log. This tells the script to start processing from that specific artist, skipping all previously processed entries.

Example command to continue from a specific point:

- Python: `python sonicratings.py -s INDEX`
- Docker Compose: `docker-compose run sonicratings -s INDEX`
- Docker Run: `docker run -t [env vars] sonicratings:local -s INDEX`

_Note: Replace `[env vars]` with the required environment variable arguments and `INDEX` with the specific index number from your log file._

## Managing Docker Containers

In this project, `docker-compose run` is used instead of `docker-compose up`. This choice allows for greater flexibility in passing command-line options directly to the script, which is essential for its varied operational modes. It's important to understand that `docker-compose run` and `docker run` create a new container each time they're executed. If you frequently run the script, you might accumulate a number of these containers. To manage this, the following method can be used to remove stopped Docker containers from your system.

**Important Note**: This command removes **all** stopped containers on your system, not just the ones related to this script. Please ensure that you do not have any other stopped containers that you want to keep before running this command. You can check your stopped containers using `docker ps -a` to ensure that removing them won't affect your other Docker projects or setups.

```console
docker container prune
```

## Mapping Provider Scores to Library Ratings

SonicRatings translates provider scores into the library's 5-star rating system. Each provider gets its score a little differently:

- **Spotify**: Uses Spotify's native track `popularity` value, which is already a 0 to 100 score.
- **TIDAL**: Multiplies the documented 0.0 to 1.0 track popularity by 100 and reuses the existing conversion without rounding.
- **Last.fm**: Derives a 0 to 100 score from three signals:
  - artist top-track position from Last.fm's `artist.getTopTracks` results
  - listener reach from the track's unique listener count
  - replay engagement from plays per listener
- **MusicBrainz**: Reads the community recording rating from MusicBrainz's recording lookup endpoint. MusicBrainz ratings are already on a 0 to 5 scale, so they are rounded directly to Navidrome's 0 to 5 rating range instead of using the 0 to 100 mapping below.

For Spotify and TIDAL, the existing conversion uses these exact ranges, without rounding:

- **0 to below 16.66**: 0 stars (Not popular; no rating write)
- **16.66 to below 33.33**: 1 star (Low popularity)
- **33.33 to below 50**: 2 stars (Moderately popular)
- **50 to below 66.66**: 3 stars (Popular)
- **66.66 to below 83.33**: 4 stars (Very popular)
- **83.33 to 100**: 5 stars (Extremely popular)

Last.fm keeps its existing weighted score (50% artist position, 40% listener reach,
10% replay bonus), rounded to an integer, without normalizing it upward:

- **5 stars**: score at least 80, artist top-track position 1-3, and at least 100,000 listeners.
- **4 stars**: score at least 65, unless the track qualifies for 5 stars.
- **0-3 stars**: the same lower ranges listed above; scores from 50 to below 65 receive 3 stars.

These conservative Last.fm cutoffs were calibrated against 519 tracks from 80 random
library albums: 24 tracks qualified for 4-5 stars, compared with 21 under the previous
conversion. They are library-based choices, not universal research-established star
thresholds. Missing artist rank cannot qualify a track for 5 stars. Existing matching,
update locks, and `--unrated-only` behavior still apply; already-rated songs are skipped
when that flag is used.

For example, TIDAL popularity `0.20` becomes 20 and receives 1 star; `0.56` becomes approximately 56 and receives 3 stars. These are popularity scores, not personal ratings or catalog percentiles. See the [TIDAL API schema](https://tidal-music.github.io/tidal-api-reference/tidal-api-oas.json).

## Estimated Processing Times

The script's processing time can vary based on several factors, including network speed and server response times. However, based on data from my own usage, I can provide a rough estimate of how long the script might take for different library sizes. The following table gives an approximate duration for processing libraries of various sizes:

| Library Size (Number of Tracks) | Estimated Processing Time |
| ------------------------------- | ------------------------- |
| 1,000                           | 0h 7m 36s                 |
| 5,000                           | 0h 38m 4s                 |
| 10,000                          | 1h 16m 8s                 |
| 50,000                          | 6h 20m 43s                |
| 100,000                         | 12h 41m 27s               |

These estimates are based on the script's performance with my library of 6,481 tracks, which took approximately 49 minutes and 21 seconds to process. Please note that these times are approximate and actual processing times may vary.

## Importance of Accurate Metadata for Track Lookup

The effectiveness of this script heavily relies on the accuracy of the artist, album, and track titles in your music library. For the supported providers to successfully recognize and match songs, these metadata details need to be precise.

I personally recommend using **MusicBrainz** to tag your music library. MusicBrainz is a comprehensive music database that provides reliable and standardized music metadata, which significantly enhances the accuracy of track matching with any of the supported providers.

However, it's important to acknowledge that even with a perfectly tagged MusicBrainz library, discrepancies can still occur between Spotify and MusicBrainz data. This may result in the script missing some songs during the matching process.

To give you an idea of the matching accuracy you can expect, here are some statistics from my own library, which is tagged using MusicBrainz:

- **Total Tracks**: 6,481
- **Tracks Matched**: 6,390
- **Tracks Not Found**: 91
- **Match Percentage**: 98.6%

## Logs

Unmatched tracks retain their existing server ratings and are not marked as
successfully updated, so later runs can retry them. Successful updates save a
fixed expiry in `logs/song_update_lock.json`; older timestamp-only entries remain
supported. `--lock-duration 0` still forces a refresh.

Logs are stored in the `logs` directory, and each script execution creates a new log file marked with a timestamp. Since these logs are retained indefinitely, you should manually delete old logs if they are no longer needed.

### Log Format

The script logs its actions in a straightforward format, using `p:49 -> r:2` to summarize operations:

- `p:49` indicates the provider score, where `49` is the specific score.
- `->` symbolizes the mapping performed by the script.
- `r:2` shows the Navidrome rating assigned based on the provider score.

### Terminal Output Colors

In the terminal, certain lines are color-coded for quick identification:

- **Red**: Denotes tracks not matched with the selected provider's data. In the logs, these are shown with `??` for popularity scores.
- **Green**: Indicates successful matches and processing of tracks.

These colors are exclusive to the terminal output for visual clarity and are not included in the log files to facilitate easier file parsing.

## Installable Automation Engine

`sonicratings_engine/` is an import-safe Python package for rating generation. Install it
with `python -m pip install .`; `sonicratings-score --help` exposes a small scoring CLI.
A future SonicRatings GUI can use the same API without importing the root `sonicratings.py` application
or starting a library sync. The existing standalone application is unchanged.

musicbrainz-helper consumes this engine for provider lookups and owns Subsonic
writes, MusicBrainz submissions, provenance and retries. arr-scripts installs both
packages and owns configuration, import hooks and scheduling. The engine does not
write ratings to either service by itself.

Engine package 0.1.0 is pinned to `engine-v0.1.0` in the Lidarr installer. Publish
that package release before deploying the new integration. Its version is separate
from the standalone application's `VERSION` file. Run its focused checks with
`python -B -m unittest discover -s tests -p test_engine.py`.
