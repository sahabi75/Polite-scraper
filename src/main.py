from pathlib import Path

import requests

BASE_URL = "https://books.toscrape.com/"
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/sahabi75/Polite-scraper)"
TIMEOUT = 10  # seconds

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

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )

    if response.status_code != 200:
        print(f"FAILED {url} (status {response.status_code})")
        return None

    response.encoding = "utf-8"
    html = response.text
    cache_path.write_text(html, encoding="utf-8")
    print(f"FETCH {url} ({len(html)} chars)")
    return html


def main():
    html = fetch_html(BASE_URL + "catalogue/page-1.html", "catalogue-page-1.html")
    if html is None:
        print("Could not get page 1, stopping.")
        return


if __name__ == "__main__":
    main()