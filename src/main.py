import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from clean import clean_and_store

START_URL = "https://books.toscrape.com/catalogue/page-1.html"
FAKE_URL = "https://books.toscrape.com/catalogue/this-book-does-not-exist_999/index.html"
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/sahabi75/Polite-scraper)"
TIMEOUT = 20  # seconds
DELAY = 0.6  # seconds between real requests (must be at least 0.5)
MAX_PAGES = 3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUT_DIR = PROJECT_ROOT / "output"

# counters for the run report
STATS = {"pages_fetched": 0, "cache_hits": 0, "failed_urls": []}


def fetch_html(url, cache_name):
    """Return the HTML for a URL. Read from cache if it exists, otherwise fetch."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / cache_name

    if cache_path.exists():
        html = cache_path.read_text(encoding="utf-8")
        STATS["cache_hits"] += 1
        print(f"CACHE HIT {url} ({len(html)} chars)")
        return html

    for attempt in (1, 2):  # one try + one retry
        time.sleep(DELAY)  # only real requests wait; cache hits never reach here
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            print(f"TIMEOUT {url} (attempt {attempt})")
            continue

        if response.status_code >= 500:
            print(f"SERVER ERROR {url} (status {response.status_code}, attempt {attempt})")
            continue

        if response.status_code != 200:
            print(f"FAILED {url} (status {response.status_code})")
            return None  # 404, 403 etc: never retry

        response.encoding = "utf-8"
        html = response.text
        cache_path.write_text(html, encoding="utf-8")
        STATS["pages_fetched"] += 1
        print(f"FETCH {url} ({len(html)} chars)")
        return html

    print(f"GIVING UP {url}")
    return None


def get_fetched_at(cache_name):
    """When the cached file was saved, as an ISO timestamp (our provenance)."""
    modified = (CACHE_DIR / cache_name).stat().st_mtime
    return datetime.fromtimestamp(modified, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- Stage 2: discover book URLs ----------

def get_book_links(html, page_url):
    """Return absolute URLs of every book listed on a catalogue page."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("article.product_pod h3 a"):
        links.append(urljoin(page_url, a["href"]))
    return links


def get_next_page_url(html, page_url):
    """Return the absolute URL of the 'next' page, or None if there isn't one."""
    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.select_one("li.next a")
    if next_link is None:
        return None
    return urljoin(page_url, next_link["href"])


def discover_books():
    """Walk the first MAX_PAGES catalogue pages.
    Returns (pages_visited, total_links_found, unique_books).
    Each unique book is {"url": ..., "source_page": ...}."""
    page_url = START_URL
    pages_visited = 0
    found = []

    while page_url and pages_visited < MAX_PAGES:
        page_number = pages_visited + 1
        html = fetch_html(page_url, f"catalogue-page-{page_number}.html")
        if html is None:
            STATS["failed_urls"].append(page_url)
            break

        for link in get_book_links(html, page_url):
            found.append({"url": link, "source_page": page_url})
        pages_visited += 1
        page_url = get_next_page_url(html, page_url)

    # remove duplicate URLs, keep the first one seen
    seen = set()
    unique_books = []
    for book in found:
        if book["url"] not in seen:
            seen.add(book["url"])
            unique_books.append(book)

    return pages_visited, len(found), unique_books


# ---------- Stage 3: extract raw records ----------

def extract_book(html, product_url, source_page, fetched_at):
    """Turn one book page into a raw record (all values still plain text)."""
    soup = BeautifulSoup(html, "html.parser")
    product = soup.select_one("article.product_page")  # only look inside the product area

    title = product.select_one("div.product_main h1").get_text(strip=True)
    price_text = product.select_one("div.product_main p.price_color").get_text(strip=True)

    availability = product.select_one("div.product_main p.availability")
    availability_text = " ".join(availability.get_text().split())

    rating_tag = product.select_one("div.product_main p.star-rating")
    rating_classes = [c for c in rating_tag["class"] if c != "star-rating"]
    rating_text = rating_classes[0] if rating_classes else None

    # the description is the <p> right after the #product_description heading
    description_tag = product.select_one("#product_description + p")
    description = description_tag.get_text(strip=True) if description_tag else None

    return {
        "title": title,
        "product_url": product_url,
        "price_text": price_text,
        "availability_text": availability_text,
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": fetched_at,
    }


def extract_all_books(books):
    """Fetch (or read from cache) every book page and extract its raw record.
    Each page is handled on its own: one bad page is logged and skipped."""
    records = []
    for book in books:
        slug = book["url"].split("/")[-2]  # e.g. a-light-in-the-attic_1000
        cache_name = f"book-{slug}.html"

        html = fetch_html(book["url"], cache_name)
        if html is None:
            STATS["failed_urls"].append(book["url"])
            continue  # skip pages that failed

        try:
            records.append(
                extract_book(html, book["url"], book["source_page"], get_fetched_at(cache_name))
            )
        except Exception as e:  # a broken page must not kill the run
            print(f"PARSE ERROR {book['url']} ({e})")
            STATS["failed_urls"].append(book["url"])
    return records


# ---------- Stage 5: run report ----------

def write_run_report(started_at, started_clock, valid, invalid):
    OUTPUT_DIR.mkdir(exist_ok=True)
    report = {
        "started_at": started_at,
        "duration_seconds": round(time.time() - started_clock, 2),
        "pages_fetched": STATS["pages_fetched"],
        "cache_hits": STATS["cache_hits"],
        "valid_records": valid,
        "invalid_records": invalid,
        "failed_pages": len(STATS["failed_urls"]),
        "failed_urls": STATS["failed_urls"],
    }
    path = OUTPUT_DIR / "run-report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Run report:")
    print(json.dumps(report, indent=2))


def main():
    started_clock = time.time()
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pages_visited, total_found, books = discover_books()
    print(f"catalogue_pages={pages_visited}")
    print(f"discovered={total_found}")
    print(f"unique_urls={len(books)}")

    # failure test: python src\main.py --test-failure
    if "--test-failure" in sys.argv:
        books.append({"url": FAKE_URL, "source_page": START_URL})
        print("TEST MODE: added one made-up book URL")

    records = extract_all_books(books)
    print(f"detail_pages={len(records)}")

    valid, invalid = clean_and_store(records)
    print(f"valid_records={valid}")
    print(f"invalid_records={invalid}")

    write_run_report(started_at, started_clock, valid, invalid)


if __name__ == "__main__":
    main()
