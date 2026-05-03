import sqlite3
import requests
import json
import time

DB_PATH = "monteurzimmer_phones.db"
COORD_URL = "https://download.geonames.org/export/zip/DE.zip"


def create_coords_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS zip_coordinates (
            zip_code TEXT PRIMARY KEY,
            lat REAL,
            lon REAL,
            city TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_zip_coord ON zip_coordinates(zip_code)")
    conn.commit()


def download_and_load_coordinates():
    print("Downloading German zip code coordinates...")
    response = requests.get(COORD_URL, timeout=60)
    response.raise_for_status()

    import zipfile
    import io

    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        with z.open("DE.txt") as f:
            content = f.read().decode("utf-8")

    conn = sqlite3.connect(DB_PATH)
    create_coords_table(conn)

    count = 0
    for line in content.splitlines():
        parts = line.split("\t")
        if len(parts) >= 11:
            zip_code = parts[1].strip()
            lat = float(parts[9])
            lon = float(parts[10])
            city = parts[2].strip()

            conn.execute(
                "INSERT OR REPLACE INTO zip_coordinates (zip_code, lat, lon, city) VALUES (?, ?, ?, ?)",
                (zip_code, lat, lon, city)
            )
            count += 1

    conn.commit()
    conn.close()
    print(f"Loaded {count} zip code coordinates")


if __name__ == "__main__":
    download_and_load_coordinates()