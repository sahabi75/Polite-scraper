import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

START_URL = "https://books.toscrape.com/catalogue/page-1.html"
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/sahabi75/Polite-scraper)"
TIMEOUT = 10  # seconds
DELAY = 0.6  # seconds between real requests (must be at least 0.5)
MAX_PAGES = 3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"


def fetch_html(url, cache_name):
    """Return the HTML for a URL. Read from cache if it exists, otherwise fetch."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / cache_name

    if cache_path.exists():
        html = cache_path.read_text(encoding="utf-8")
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
        print(f"FETCH {url} ({len(html)} chars)")
        return html

    print(f"GIVING UP {url}")
    return None


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


def discover_book_urls():
    """Walk the first MAX_PAGES catalogue pages and collect book URLs."""
    page_url = START_URL
    pages_visited = 0
    all_links = []

    while page_url and pages_visited < MAX_PAGES:
        page_number = pages_visited + 1
        html = fetch_html(page_url, f"catalogue-page-{page_number}.html")
        if html is None:
            break

        all_links.extend(get_book_links(html, page_url))
        pages_visited += 1
        page_url = get_next_page_url(html, page_url)

    # remove duplicates but keep the original order
    unique_links = list(dict.fromkeys(all_links))
    return pages_visited, all_links, unique_links


def main():
    pages_visited, all_links, unique_links = discover_book_urls()
    print(f"catalogue_pages={pages_visited}")
    print(f"discovered={len(all_links)}")
    print(f"unique_urls={len(unique_links)}")


if __name__ == "__main__":
    main()