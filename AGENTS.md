# Monteur

Small Python project: scrapes phone numbers from monteurzimmer.de into SQLite, serves them via Flask API.

## Scripts

- `scraper.py` - Run standalone to scrape all German listings. Uses 1.5s delay, commits every 100 listings.
- `api.py` - Flask API on port 5001 (not 5000). Run directly: `python api.py`
- `load_coords.py` - Downloads German zip coordinates from GeoNames and loads into `monteurzimmer_phones.db`

## Database

- `monteurzimmer_phones.db` - SQLite with `phone_numbers` and `zip_coordinates` tables. 22MB committed to git.

## Dependencies

`requirements.txt` only (requests, beautifulsoup4). No test/lint/typecheck tooling configured.