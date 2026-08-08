"""
Stage 2: discover the three catalogue pages and every book URL.

Following the catalogue's own "next" links, collecting relative book links,
turning them into absolute URLs, and removing duplicates. Cached pages cost no
delay; real requests wait at least 500 ms (the fetch_page delay).
"""
import os
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")

USER_AGENT = (
    "FlyRankInternship-A9/1.0 "
    "(polite scraper; repo: https://github.com/rehanalicreates/flyrank-backend-track)"
)
TIMEOUT = 10  # seconds; give up, never wait forever
DELAY = 0.5   # seconds between real requests to the site


def fetch_page(url: str, cache_name: str, delay: float = 0.0) -> tuple[str, bool]:
    """Return (html, from_cache). Downloads and caches on first use; reads cache after."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_name)

    if os.path.isfile(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read(), True

    if delay:
        time.sleep(delay)  # be a polite guest between real requests

    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"fetch failed: {url} -> HTTP {resp.status_code}")

    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(resp.text)
    return resp.text, False


def catalogue_pages(start_url: str) -> list[tuple[str, str]]:
    """Follow the catalogue's own 'next' link from page 1. Returns [(url, cache_name)]."""
    pages = []
    url, cache = start_url, "catalogue-page-1.html"
    while True:
        pages.append((url, cache))
        html, _ = fetch_page(url, cache)
        soup = BeautifulSoup(html, "html.parser")
        next_li = soup.select_one("li.next > a")
        if next_li is None:
            break
        url = urljoin(url, next_li.get("href"))
        n = len(pages) + 1
        cache = f"catalogue-page-{n}.html"
        if len(pages) >= 3:
            break  # the assignment scope: first 3 catalogue pages only
    return pages


def book_links_from(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("article.product_pod h3 a"):
        href = a.get("href")
        if href:
            links.append(urljoin(page_url, href))
    return links


def main() -> None:  # noqa: C901
    pages = catalogue_pages(BASE_URL + "catalogue/page-1.html")
    print(f"catalogue_pages={len(pages)}")

    all_links: list[str] = []
    for url, cache in pages:
        html, _ = fetch_page(url, cache)
        all_links.extend(book_links_from(html, url))
    unique = sorted(set(all_links))
    print(f"discovered={len(all_links)}  unique_urls={len(unique)}")


if __name__ == "__main__":
    sys.exit(main())
