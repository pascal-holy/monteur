#!/usr/bin/env python3
"""
Monteurzimmer.de Phone Number Scraper - Germany Only
Scrapes phone numbers from all German listings and stores in SQLite.
Records ALL phone numbers per city - no deduplication.
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
import json
from urllib.parse import urljoin, urlparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.monteurzimmer.de"
DELAY = 1.5
CHECKPOINT_INTERVAL = 100

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

DB_PATH = "monteurzimmer_phones.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            phone_type TEXT,
            listing_url TEXT,
            listing_title TEXT,
            zip_code TEXT,
            city TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_phone ON phone_numbers(phone_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_zip ON phone_numbers(zip_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON phone_numbers(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listing ON phone_numbers(listing_url)")
    conn.commit()
    return conn


def get_soup(url, session):
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, 'html.parser')


def extract_phones_from_detail_page(soup, listing_url, conn):
    phones_found = 0
    phones_data = []

    listing_title = ''
    h1 = soup.find('h1')
    if h1:
        listing_title = h1.get_text(strip=True)
    if not listing_title:
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'LodgingBusiness':
                    listing_title = data.get('name', '')
                    break
            except:
                pass

    tel_links = soup.find_all('a', href=re.compile(r'^tel:'))
    for link in tel_links:
        href = link.get('href', '')
        phone = href.replace('tel:', '').replace('+49', '0')
        if len(phone) >= 10:
            is_handy = False
            parent = link.find_parent(['span', 'div'])
            if parent:
                parent_text = parent.get_text().lower()
                is_handy = 'handy' in parent_text
            phones_data.append((phone, 'Handy' if is_handy else 'Telefon'))

    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if 'telephone' in data:
                    phone = data['telephone'].replace('+49', '0')
                    if len(phone) >= 10:
                        phones_data.append((phone, 'Telefon'))
        except:
            pass

    for phone, ptype in phones_data:
        conn.execute(
            """INSERT INTO phone_numbers
               (phone_number, phone_type, listing_url, listing_title)
               VALUES (?, ?, ?, ?)""",
            (phone, ptype, listing_url, listing_title)
        )
        phones_found += 1

    return phones_found


def extract_zip_and_city(soup):
    zip_code = ''
    city = ''

    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'LodgingBusiness':
                if 'address' in data and isinstance(data['address'], dict):
                    addr = data['address']
                    zip_code = addr.get('postalCode', '')
                    city = addr.get('addressLocality', '')
                    if zip_code or city:
                        return zip_code, city
        except:
            pass

    addr_div = soup.find('div', class_=re.compile(r'adresse|address', re.I))
    if not addr_div:
        for h in soup.find_all(['h2', 'h3'], string=re.compile(r'Adresse', re.I)):
            parent = h.find_parent(['div', 'section'])
            if parent:
                addr_div = parent
                break

    if addr_div:
        addr_text = addr_div.get_text()
        zip_match = re.search(r'\b(\d{5})\b', addr_text)
        if zip_match:
            zip_code = zip_match.group(1)
        city_match = re.search(r'\d{5}[^\d]*([A-Za-zäöüß\- ]+?)(?:,|$)', addr_text)
        if city_match:
            city = city_match.group(1).strip()

    return zip_code, city


def get_german_cities(session):
    logger.info("Fetching German city list from all alphabet pages...")
    all_cities = []
    alphabet_pages = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l',
                      'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'z']

    for letter in alphabet_pages:
        url = f"{BASE_URL}/deutschland/st%C3%A4dte/{letter}"
        try:
            soup = get_soup(url, session)
            for link in soup.find_all('a', href=re.compile(r'^/unterkunft/')):
                href = link.get('href', '')
                if '/stadtteil/' in href:
                    continue
                match = re.search(r'/unterkunft/([^/]+)/(\d+)', href)
                if match:
                    city_slug, city_id = match.groups()
                    all_cities.append({
                        'name': link.get_text(strip=True),
                        'url': f"{BASE_URL}{href}",
                        'slug': city_slug,
                        'city_id': city_id
                    })
            logger.info(f"  Fetched {letter.upper()} - total so far: {len(all_cities)}")
            time.sleep(1)
        except Exception as e:
            logger.error(f"  Error fetching {letter}: {e}")

    seen = set()
    unique_cities = []
    for c in all_cities:
        if c['url'] not in seen:
            seen.add(c['url'])
            unique_cities.append(c)

    logger.info(f"Found {len(unique_cities)} unique German cities/regions")
    return unique_cities


def get_listing_urls_from_page(soup, base_url):
    urls = []
    for link in soup.find_all('a', href=True):
        if link.find_parent(class_='extended-headline'):
            break
        href = link.get('href', '')
        if any(p in href for p in ['/unterkuenfte/', '/wohnung/', '/haus/', '/gaestezimmer/']):
            if '/stadtteil/' not in href:
                full_url = urljoin(base_url, href)
                if full_url not in urls:
                    urls.append(full_url)
    return urls


def main():
    session = requests.Session()
    conn = init_db()

    stats = {
        'cities_processed': 0,
        'pages_processed': 0,
        'listings_processed': 0,
        'phones_found': 0
    }

    cities = get_german_cities(session)

    for city in cities:
        logger.info(f"Processing city: {city['name']} ({city['url']})")
        page = 1
        city_has_listings = True
        city_phones = 0

        while city_has_listings:
            if page == 1:
                url = city['url']
            else:
                url = f"{city['url']}?page={page}"

            try:
                soup = get_soup(url, session)
                listing_urls = get_listing_urls_from_page(soup, BASE_URL)

                if not listing_urls:
                    city_has_listings = False
                    break

                for listing_url in listing_urls:
                    try:
                        listing_soup = get_soup(listing_url, session)
                        zip_code, city_name = extract_zip_and_city(listing_soup)

                        p = extract_phones_from_detail_page(listing_soup, listing_url, conn)

                        if p > 0 and (zip_code or city_name):
                            conn.execute(
                                """UPDATE phone_numbers
                                   SET zip_code = ?, city = ?
                                   WHERE listing_url = ? AND (zip_code IS NULL OR zip_code = '' OR city IS NULL OR city = '')""",
                                (zip_code or '', city_name or '', listing_url)
                            )

                        city_phones += p
                        stats['phones_found'] += p
                        stats['listings_processed'] += 1

                        if stats['listings_processed'] % CHECKPOINT_INTERVAL == 0:
                            conn.commit()
                            logger.info(f"Checkpoint: {stats['listings_processed']} listings, {stats['phones_found']} phones")

                    except Exception as e:
                        logger.error(f"Error processing {listing_url}: {e}")

                    time.sleep(DELAY)

                stats['pages_processed'] += 1
                page += 1
                time.sleep(DELAY)

            except Exception as e:
                logger.error(f"Error processing page {page} of {city['name']}: {e}")
                break

        stats['cities_processed'] += 1
        logger.info(f"Completed {city['name']} - {city_phones} phones found in this city")

    conn.commit()
    conn.close()

    logger.info("=" * 50)
    logger.info("SCRAPING COMPLETE")
    logger.info(f"Cities processed: {stats['cities_processed']}")
    logger.info(f"Pages processed: {stats['pages_processed']}")
    logger.info(f"Listings processed: {stats['listings_processed']}")
    logger.info(f"Total phone records: {stats['phones_found']}")
    logger.info(f"Database saved to: {DB_PATH}")


if __name__ == "__main__":
    main()