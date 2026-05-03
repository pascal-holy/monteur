import sqlite3
import math
from flask import Flask, jsonify, request

app = Flask(__name__)
DATABASE = "monteurzimmer_phones.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@app.route("/phones/<zip_code>", methods=["GET"])
def get_phones_by_zip(zip_code):
    radius = request.args.get("radius", 10, type=float)
    unit = request.args.get("unit", "km")

    conn = get_db_connection()

    coord_row = conn.execute("SELECT lat, lon FROM zip_coordinates WHERE zip_code = ?", (zip_code,)).fetchone()

    if not coord_row:
        conn.close()
        return jsonify({"error": "zip code not found in coordinates database"}), 404

    base_lat, base_lon = coord_row["lat"], coord_row["lon"]

    rows = conn.execute("""SELECT phone_number, phone_type, listing_title, city, zip_code
                           FROM phone_numbers WHERE zip_code != ''""").fetchall()

    results = []
    for row in rows:
        coord = conn.execute("SELECT lat, lon FROM zip_coordinates WHERE zip_code = ?",
                             (row["zip_code"],)).fetchone()
        if coord:
            dist = haversine(base_lat, base_lon, coord["lat"], coord["lon"])
            if dist <= radius:
                result = dict(row)
                result["distance_km"] = round(dist, 2)
                results.append(result)

    conn.close()

    results.sort(key=lambda x: x["distance_km"])
    return jsonify({"zip_code": zip_code, "radius_km": radius, "count": len(results), "phones": results})


if __name__ == "__main__":
    app.run(debug=True, port=5001)