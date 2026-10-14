# SonicRatings

Bring track popularity and community ratings into your Navidrome or Subsonic-compatible music library. SonicRatings supports Spotify, TIDAL, Last.fm, MusicBrainz, and Discogs as rating sources.

SonicRatings works especially well alongside [navidrome-smart-playlists](https://github.com/SickProdigy/navidrome-smart-playlists). SonicRatings supplies the track ratings, while its Navidrome `.NSP` smart playlist definitions can use those ratings to build dynamic playlists of highly rated music by genre or decade. Run SonicRatings first, then refresh the playlists with a Navidrome library scan.

Originally called **SPTNR** (Spotify Popularity to Navidrome Ratings), this script was developed to repurpose the star ratings in Navidrome. As a Navidrome user who utilizes the 'favorite' feature instead of star ratings, I wanted to give new life and utility to the unused rating system. By mapping provider scores to library ratings, SonicRatings provides a quick way to identify popular tracks. This becomes particularly useful when frequently adding new albums and artists, especially those you're not familiar with.

The installed command and Python package are both `sonicratings`; the Compose service is also `sonicratings`. The Docker examples below build and use the local image `sonicratings:local`.

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
14. [Package and Automation](#package-and-automation)

## Features

- **Spotify Integration**: Connects to Spotify's API to fetch popularity data for tracks.
- **TIDAL Support**: Uses TIDAL catalog popularity with the same star conversion as Spotify. Requires TIDAL developer app credentials, not Spotify credentials.
- **Last.fm Support**: Can use Last.fm artist top-track position, listeners, and playcounts as an alternate popularity source. (A useful alternative when you want broader catalog coverage.)
- **MusicBrainz Support**: Can use MusicBrainz community ratings as a rating source. (Currently not a lot of ratings available, but worth having as an option for the future.)
- **Discogs Support**: Preview release ratings and optionally apply them to matching tracks. These are inherited album/edition ratings, with vote counts and release IDs shown in the logs.
- **Subsonic/Navidrome Integration**: Updates personal track ratings through the Subsonic API based on provider scores.
- **Flexible Processing**: Process specific artists, albums, or a range of artists or albums.
- **Unrated-Only Mode**: Skip tracks that already have a rating and only update unrated songs.
- **Preview Mode**: Run the script in preview mode to see changes without making any actual updates.
- **Logging**: Detailed logging of the process, both in the console and to a file.
- **Docker Support**: Run the script in a Docker container for consistent environments and ease of use.

## Requirements

- Python 3.10 or newer, or Docker
- Access to a Navidrome or compatible Subsonic server
- Spotify client ID and client secret for the default Spotify provider ([Developer dashboard](https://developer.spotify.com/dashboard/create))
- Optional: a Last.fm API key if you want to use Last.fm as the popularity provider
- Optional: TIDAL developer app credentials if you want to use TIDAL
- MusicBrainz community rating lookups do not require provider credentials
- Optional: a Discogs personal access token (`DISCOGS_TOKEN`) if anonymous access is insufficient

**Compatibility Note**: SonicRatings is designed for Navidrome and uses the Subsonic API. It should work with any Subsonic/Navidrome server supporting the required browsing, personal-rating, and authentication APIs. Other server implementations have not been tested live. If you successfully use it with another server, please open an issue so I can document compatibility and assist others.

## Quick Start

Build SonicRatings from this checkout, then replace the environment variable values below with your own:

```console
docker build -t sonicratings:local .
```

```console
docker run --rm -t \
  -v sonicratings-logs:/usr/src/app/logs \
  -e NAV_BASE_URL=your_navidrome_server_url \
  -e NAV_USER=your_navidrome_username \
  -e NAV_PASS=your_navidrome_password \
  -e SPOTIFY_CLIENT_ID=your_spotify_client_id \
  -e SPOTIFY_CLIENT_SECRET=your_spotify_client_secret \
  sonicratings:local
```

For Last.fm, add `-e LASTFM_API_KEY=your_lastfm_api_key` and `--provider lastfm`. MusicBrainz uses `--provider musicbrainz` without provider credentials. Only the selected provider needs credentials; TIDAL setup is described below.

The `sonicratings-logs` Docker volume keeps logs and update locks between runs. Compose below uses a local `./logs` directory instead.

**Note**: The `-t` flag is used to allocate a pseudo-terminal which assists in displaying colored and bold text in the terminal output, which this script uses.

### Using Docker Compose

1. **Create `docker-compose.yml` File**: Set up your `docker-compose.yml` file with the following content, replacing the environment variables with your own details:

   ```yaml
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
         - LASTFM_API_KEY=${LASTFM_API_KEY:-}
       volumes:
         - ./logs:/usr/src/app/logs
   ```

For Last.fm, set `LASTFM_API_KEY` in `.env` and run with `--provider lastfm`. For TIDAL, add its credentials to the service and run with `--provider tidal`. The [Compose example](docker-compose.yml.example) includes all provider settings.

2. **Run the Script**: Execute the Docker Compose command to run the script:

   ```console
   docker compose run --rm sonicratings
   ```

## Running Natively or Building Locally

For those who prefer running the script natively using Python or building the Docker image locally, the following steps apply:

### Running Natively (Without Docker)

Requires Python 3.10 or newer. From the repository, create an environment and install the package.

Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
```

Keep your existing `.env` when upgrading. Configure your server and selected provider using [.env.example](.env.example). Editable installation makes the command use local source changes immediately. Activate the environment again in each new terminal.

Preview a backfill of unrated songs:

```bash
sonicratings --provider lastfm --unrated-only --preview
```

Apply the same backfill:

```bash
sonicratings --provider lastfm --unrated-only
```

`sonicratings --help` lists all options. From the checkout you can also use `python -m sonicratings` with the same options. Run from the repository to reuse your existing `.env` and `logs/song_update_lock.json`; elsewhere, select them explicitly with `--env-file PATH` and `--log-dir PATH`.

### Building and Running with Docker Locally

1. **Clone the Repository**: Clone the full repository to your local machine so the local Docker build includes the matching and provider modules.

2. **Configure Docker Compose**: Copy the example and edit your `docker-compose.yml`:

   ```console
   cp docker-compose.yml.example docker-compose.yml
   # Edit the docker-compose.yml file
   ```

3. **Check the Docker Image Source**: The example uses `build: .` and the local image tag `sonicratings:local`.

4. **Build and Run**: Build the Docker image and run the script:

   ```console
   docker compose build
   docker compose run --rm sonicratings [options]
   ```

## Usage

The script supports various options for flexible usage. Below are examples of how to run the script with different options, using the installed command, Docker Compose, and Docker Run. Replace `[options]` with any of the specified options based on your needs.

### Options

- `-p, --preview`: Look up and display ratings without writing ratings or update locks. Existing locks still apply; add `--lock-duration 0` to preview every selected track.
- `-a, --artist ARTIST_ID`: Process a specific artist. Multiple artists can be specified.
- `-b, --album ALBUM_ID`: Process a specific album. Multiple albums can be specified.
- `-s, --start START_INDEX`: Start processing from the artist at the specified index (0-based).
- `-l, --limit LIMIT`: Limit the processing to a specific number of artists from the start index.
- `-d, --lock-duration DURATION`: Number of days to lock song updates. Defaults to 7; 0 disables the update lock, while `--unrated-only` still skips already-rated songs.
- `-j, --lock-jitter HOURS`: Spread new lock expiries across a window of this many hours around the base duration. Defaults to 24 (up to 12 hours earlier or later).
- `--navidrome-retries RETRIES`: Number of attempts for Navidrome API requests. Defaults to 3.
- `--navidrome-timeout SECONDS`: Base timeout for Navidrome API requests. Defaults to 10 seconds and increases on each retry.
- `--provider spotify|lastfm|musicbrainz|tidal|discogs`: Choose the source used to derive the rating. Spotify is the default.
- `--discogs-inherit-album-rating`: Explicitly allow Discogs release ratings to be written to matching tracks. Required when applying Discogs ratings; preview works without it.
- `--discogs-min-votes VOTES`: Minimum votes for a Discogs release rating. Defaults to 5; must be positive.
- `--discogs-release ALBUM_ID=RELEASE_ID`: Select a specific Discogs edition for a Navidrome album. Repeat for multiple albums. Artist, album, and track matching checks still apply.
- `--unrated-only`: Only update songs that do not already have a Navidrome rating.
- `--env-file PATH`: Load configuration from this file; defaults to `.env` in the current directory. Existing environment variables take precedence.
- `--log-dir PATH`: Store logs and update locks here; defaults to `logs/`. Reuse the same directory to retain existing update history.
- `-v, --version`: Show the SonicRatings package version.

### Command Formats

1. **Running Natively (Installed Command)**:

   ```console
   sonicratings [options]
   ```

2. **Using Docker Compose**:

   ```console
   docker compose run --rm sonicratings [options]
   ```

3. **Using Docker Run**:
   ```console
   docker run --rm -t [environment variables] sonicratings:local [options]
   ```

## Examples

- **Preview Mode**:
  Run the script in preview mode to see changes without making any actual updates.

  - Python: `sonicratings -p`
  - Docker Compose: `docker compose run --rm sonicratings -p`
  - Docker Run: `docker run --rm -t [env vars] sonicratings:local -p`

- **Process Specific Artist**:
  Process only one artist by specifying their ID.

  - Python: `sonicratings -a artist_id`
  - Docker Compose: `docker compose run --rm sonicratings -a artist_id`
  - Docker Run: `docker run --rm -t [env vars] sonicratings:local -a artist_id`

- **Process Specific Albums**:
  Process multiple specific albums by specifying their IDs.

  - Python: `sonicratings -b album_id1 -b album_id2`
  - Docker Compose: `docker compose run --rm sonicratings -b album_id1 -b album_id2`
  - Docker Run: `docker run --rm -t [env vars] sonicratings:local -b album_id1 -b album_id2`

- **Process Range of Artists**:
  Process artists starting from a certain index with a limit.
  - Python: `sonicratings -s 10 -l 5`
  - Docker Compose: `docker compose run --rm sonicratings -s 10 -l 5`
  - Docker Run: `docker run --rm -t [env vars] sonicratings:local -s 10 -l 5`

- **Only Update Unrated Songs**:
   Skip tracks that already have a rating in Navidrome.
   - Python: `sonicratings --unrated-only`
   - Docker Compose: `docker compose run --rm sonicratings --unrated-only`
   - Docker Run: `docker run --rm -t [env vars] sonicratings:local --unrated-only`

- **Tolerate Slow Navidrome Scans**:
   Retry Navidrome API calls and increase the timeout for each retry.
   - Python: `sonicratings --navidrome-retries 3 --navidrome-timeout 10`
   - Docker Compose: `docker compose run --rm sonicratings --navidrome-retries 3 --navidrome-timeout 10`
   - Docker Run: `docker run --rm -t [env vars] sonicratings:local --navidrome-retries 3 --navidrome-timeout 10`

- **Use Last.fm as the Provider**:
   Use Last.fm artist top-track position, listener, and playcount data instead of Spotify popularity.
   - Python: `LASTFM_API_KEY=... sonicratings --provider lastfm`
   - Docker Compose: `docker compose run --rm -e LASTFM_API_KEY=... sonicratings --provider lastfm`
   - Docker Run: `docker run --rm -t -e LASTFM_API_KEY=... [env vars] sonicratings:local --provider lastfm`

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
   - Python: `sonicratings --provider musicbrainz`
   - Docker Compose: `docker compose run --rm sonicratings --provider musicbrainz`
   - Docker Run: `docker run --rm -t [env vars] sonicratings:local --provider musicbrainz`

### Use TIDAL as the Provider

Create an app in the [TIDAL developer portal](https://developer.tidal.com/) and set `TIDAL_CLIENT_ID` and `TIDAL_CLIENT_SECRET` in `.env` or your Compose environment. Set `TIDAL_COUNTRY_CODE` to your two-letter catalog country (default: `US`). Catalog lookup uses the client credentials flow; your personal TIDAL login and Spotify credentials are not required.

Preview before applying:

```console
sonicratings --provider tidal --unrated-only --preview
```

For the local Docker build:

```console
docker compose build sonicratings
docker compose run --rm sonicratings --provider tidal --unrated-only --preview
```

Remove `--preview` to apply ratings. Searches require matching artist and title (including version), preferring matching albums. Missing matches or missing/invalid popularity preserve existing ratings. Scores mapping to zero do not write a rating or an update lock, so unrated tracks remain eligible on later runs, subject to any existing lock. API failures stop the run rather than clearing ratings.

### Use Discogs as the Provider

Discogs rates releases rather than individual songs. Automatic matching uses the designated main release of a uniquely matched master; it is an edition's rating, not an average across editions. If no master matches, a unique matching release can be used. Ambiguous matches, missing ratings, and releases below the minimum vote count preserve existing track ratings.

Preview first, including tracks with active locks:

```console
sonicratings --provider discogs --preview --lock-duration 0 -b album_id
```

To apply the release's rating to matching songs, explicitly enable inheritance:

```console
sonicratings --provider discogs --discogs-inherit-album-rating --unrated-only
```

Track titles and performers must match the release's tracklist; live/remix/version words are retained. Compilation matching uses the album artist for the release and each song's performer for its track. Logs identify the Discogs release, selection method, vote count, and inherited rating. Native artist ratings and separate album-rating writes are not included.

Use `--discogs-release album_id=2879` to choose a particular edition. The [Discogs release ID](https://www.discogs.com/release/2879) is the number in its release URL, not a master ID. Ratings need at least five votes by default (`--discogs-min-votes` changes this); averages are rounded to the nearest star, with halves rounded up.

Requests are paced conservatively and album lookups are cached for the run. Anonymous access was tested successfully; if access is denied, set `DISCOGS_TOKEN` to a personal access token from [Discogs developer settings](https://www.discogs.com/settings/developers). For Compose, pass it as `DISCOGS_TOKEN=${DISCOGS_TOKEN:-}` in the service environment, as the example file does. API failures stop the run without writing a rating for the failed lookup. The reusable client is available from `sonicratings.discogs`.

For Docker, rebuild the image and use the same options with `docker compose run --rm sonicratings`.

## Resuming Interrupted Sessions

In cases where your session gets interrupted - for instance, if your machine goes to sleep, you encounter rate limits from Spotify, or for any other reason that causes the script to not complete - you have the option to resume from where you left off.

To determine the point of interruption, check the log file. The log entry will contain details of the artist it failed on, along with the index in a format similar to: `Artist: ARTIST_NAME (ARTIST_NAVIDROME_ID)[INDEX]`. Here, the index is enclosed in brackets.

Restart with the same provider and processing options, adding `-s INDEX` from the log. This starts again at the interrupted artist; successful updates within that artist are skipped while their locks remain active. For runs selected with `--artist` or `--album`, rerun those IDs instead.

Example command to continue from a specific point:

- Python: `sonicratings -s INDEX`
- Docker Compose: `docker compose run --rm sonicratings -s INDEX`
- Docker Run: `docker run --rm -t [env vars] sonicratings:local -s INDEX`

_Note: Replace `[env vars]` with the required environment variable arguments and `INDEX` with the specific index number from your log file._

## Managing Docker Containers

Use `docker compose run --rm sonicratings [options]` or `docker run --rm ...` for one-off runs. `--rm` removes the container after it exits; mount `/usr/src/app/logs` to preserve logs and update locks between runs, as the Compose example does.

## Mapping Provider Scores to Library Ratings

SonicRatings translates provider scores into the library's 5-star rating system. Each provider gets its score a little differently:

- **Spotify**: Uses Spotify's native track `popularity` value, which is already a 0 to 100 score.
- **TIDAL**: Multiplies the documented 0.0 to 1.0 track popularity by 100 and reuses the existing conversion without rounding.
- **Last.fm**: Derives a 0 to 100 score from three signals:
  - artist top-track position from Last.fm's `artist.getTopTracks` results
  - listener reach from the track's unique listener count
  - replay engagement from plays per listener
- **MusicBrainz**: Reads the community recording rating from MusicBrainz's recording lookup endpoint. MusicBrainz ratings are already on a 0 to 5 scale, so they are rounded directly to Navidrome's 0 to 5 rating range instead of using the 0 to 100 mapping below.
- **Discogs**: Uses a release's 1Ã¢â‚¬â€œ5 community average, rounded directly to stars after checking the vote count. Applying it to tracks requires `--discogs-inherit-album-rating`; it represents the release's rating rather than each song's individual popularity.

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

Rough times to preview a whole library, including already-rated tracks, with no tracks skipped:

| Library Size (Tracks) | Last.fm Preview | MusicBrainz Preview |
| ------------------------------- | ------- | ----------- |
| 1,000                           | ~10 minutes | ~50 minutes |
| 5,000                           | ~45 minutes | ~4 hours |
| 10,000                          | ~1.5 hours | ~8 hours |
| 50,000                          | ~7 hours | ~2 days |
| 100,000                         | ~14 hours | ~3.5 days |

Actual updates also write ratings and save locks, so they take longer. Metadata, network speed, retries, and large lock files affect runtime; skipping rated or locked tracks speeds repeat runs. Representative timings are not yet available for Spotify, TIDAL, or Discogs.

*Timing basis: 237 tracks across 48 random albums, tested October 13, 2026 with SonicRatings v1.3.0 (Windows/Python 3.14), using `--preview --lock-duration 0` without `--unrated-only`. Rounded projections; revisit after performance changes.*

## Importance of Accurate Metadata for Track Lookup

The effectiveness of this script heavily relies on the accuracy of the artist, album, and track titles in your music library. For the supported providers to successfully recognize and match songs, these metadata details need to be precise.

I personally recommend using **MusicBrainz** to tag your music library. MusicBrainz is a comprehensive music database that provides reliable and standardized music metadata, which significantly enhances the accuracy of track matching with any of the supported providers.

However, it's important to acknowledge that even with a perfectly tagged MusicBrainz library, discrepancies can still occur between Spotify and MusicBrainz data. This may result in the script missing some songs during the matching process.

The following historical Spotify sample came from my MusicBrainz-tagged library. It describes that run, rather than expected matching accuracy for the current library or other providers:

- **Total Tracks**: 6,481
- **Tracks Matched**: 6,390
- **Tracks Not Found**: 91
- **Match Percentage**: 98.6%

## Logs

Unmatched tracks retain their existing server ratings and are not marked as
successfully updated, so later runs can retry them. Successful updates save a
fixed expiry in `logs/song_update_lock.json`; older timestamp-only entries remain
supported. `--lock-duration 0` bypasses update locks; `--unrated-only` still skips already-rated songs.

Logs are stored in the `logs` directory, and each script execution creates a new log file marked with a timestamp. Since these logs are retained indefinitely, you should manually delete old logs if they are no longer needed.

### Log Format

The script logs its actions in a straightforward format, using `p:49 -> r:2` to summarize operations:

- `p:49` indicates the provider score, where `49` is the specific score.
- `->` symbolizes the mapping performed by the script.
- `r:2` shows the calculated Navidrome rating; preview mode displays it without applying it.
- MusicBrainz uses `s:` for its 0-5 community rating instead of `p:`.
- Discogs uses `discogs-release:` for the inherited release average and logs its release ID and vote count.
- The final `Found` count records successful rating writes, so `Found` and `Match` remain zero in preview mode even when lookups match. Tracks skipped by update locks are excluded from the final `Tracks` count.

### Terminal Output Colors

In the terminal, certain lines are color-coded for quick identification:

- **Red**: Denotes tracks not matched with the selected provider's data. In the logs, these are shown with `??` for popularity scores.
- **Green**: Indicates successful matches and processing of tracks.

These colors are exclusive to the terminal output for visual clarity and are not included in the log files to facilitate easier file parsing.

## Package and Automation

All implementation lives in the [sonicratings](sonicratings/) package. Root script wrappers and the separately versioned `sonicratings-engine` package have been replaced by one installable application.

| Module | Purpose |
| --- | --- |
| [cli.py](sonicratings/cli.py) | Full library sync, artist/album selection, provider scoring, previews, and update locks. |
| [lastfm_matching.py](sonicratings/lastfm_matching.py) | Last.fm spelling variants and artist/title/version matching. |
| [tidal.py](sonicratings/tidal.py) | TIDAL authentication, catalog matching, and popularity lookup. |
| [discogs.py](sonicratings/discogs.py) | Discogs release matching, vote checks, and album ratings. |
| [automation.py](sonicratings/automation.py) | Durable Lidarr import queue, server matching, retry worker, and generated-rating provenance. |
| [score.py](sonicratings/score.py) | Optional `sonicratings-score` calculator using the same Last.fm scoring as the sync. |

For automation, install a published SonicRatings release and call `sonicratings` with explicit configuration and runtime paths. The same command runs manually and inside Docker. An imported album can be selected using its **Subsonic/Navidrome album ID**:

```bash
sonicratings --provider musicbrainz --album NAVIDROME_ALBUM_ID --unrated-only --preview \
  --env-file /path/to/sonicratings.env --log-dir /path/to/sonicratings-logs
```

A Lidarr album ID is a different identifier. Arr-scripts integration will need to wait for the server import and resolve the matching Subsonic/Navidrome album before invoking this command. The queue adapter accepts Lidarr album IDs, snapshots embedded identities locally, and waits for matching tracks on the server:

```bash
sonicratings enqueue --state-dir logs/import-queue --album-id LIDARR_ALBUM_ID
sonicratings work --state-dir logs/import-queue --provider lastfm --preview
sonicratings work --state-dir logs/import-queue --provider lastfm
```

Configure `LIDARR_URL` and `LIDARR_API_KEY` for enqueue, plus `SUBSONIC_URL`, `SUBSONIC_USERNAME`, and `SUBSONIC_PASSWORD` (or the existing `NAV_BASE_URL`, `NAV_USER`, and `NAV_PASS`). Queue commands load `.env`; `--env-file PATH` selects another file. `work` and `library` preserve existing personal ratings. Queue state, logs, locks, and `generated-ratings.json` are scoped by server URL and username beneath `--state-dir`.

For a whole-library backfill through the same adapter:

```bash
sonicratings library --state-dir logs/import-queue --provider musicbrainz --preview
```

Remove `--preview` to apply. Preview retains queued work and does not write ratings, provenance, or update locks. Failed/missing matches stay queued with retry delays up to one hour; duplicate callbacks retain pending retry state. Discogs still requires `--discogs-inherit-album-rating` for writes. `sonicratings work --help` lists adapter options.

Arr-scripts installs this package independently of musicbrainz-helper and calls these commands from its background service. It supplies provenance to the contribution worker so MusicBrainz-derived stars are not submitted back as fresh votes. See the arr-scripts ratings guide for configuration and release pins.

Successful writes and pending write intents retain their source in `generated-ratings.json`. A caller can provide that file to a contribution tool without either package importing the other.

SonicRatings writes ratings to Navidrome/Subsonic. musicbrainz-helper independently contributes ratings and genres to MusicBrainz. Neither tool imports or installs the other.

Package and application version are **1.4.0**. `VERSION`, package metadata, and `sonicratings.__version__` agree. The old `engine-v0.1.0` release is superseded for future installation. Existing source-checkout users should reinstall with `python -m pip install -e .` and replace `python sonicratings.py` commands with `sonicratings` or `python -m sonicratings`.

Run checks with `python -B -m unittest discover -s tests`.
