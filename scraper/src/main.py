"""
Stage 1-3: fetch/cache, discover three catalogue pages + 60 book URLs,
extract the eight raw fields per book from the cached detail pages.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

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


def cache_name_for(url: str) -> str:
    m = re.search(r"/catalogue/[^/]*?([0-9]+)/index\.html", url)
    book_id = m.group(1) if m else "book"
    return f"detail-{book_id}.html"


def extract_raw_record(html: str, url: str, source_page: str) -> dict:
    """Pull the eight raw fields out of a book's detail page."""
    soup = BeautifulSoup(html, "html.parser")
    product = soup.select_one("article.product_page") or soup

    title_el = product.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else None

    price_el = product.select_one("p.price_color")
    price_text = price_el.get_text(strip=True) if price_el else None

    avail_el = product.select_one("p.availability")
    availability_text = avail_el.get_text(strip=True) if avail_el else None

    star_el = product.select_one("p.star-rating")
    rating_text = None
    if star_el and star_el.get("class"):
        rating_text = star_el["class"][-1]

    desc_el = product.select_one("div#product_description + p")
    description = desc_el.get_text(strip=True) if desc_el else None

    return {
        "title": title,
        "product_url": url,
        "price_text": price_text,
        "availability_text": availability_text,
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:  # noqa: C901
    pages = catalogue_pages(BASE_URL + "catalogue/page-1.html")
    print(f"catalogue_pages={len(pages)}")

    book_sources: dict[str, str] = {}
    for url, cache in pages:
        html, _ = fetch_page(url, cache)
        for link in book_links_from(html, url):
            book_sources.setdefault(link, url)
    all_links = list(book_sources.keys())
    unique = sorted(set(all_links))
    print(f"discovered={len(all_links)}  unique_urls={len(unique)}")

    raw_records = []
    for i, book_url in enumerate(unique, 1):
        html, from_cache = fetch_page(book_url, cache_name_for(book_url), delay=DELAY)
        source_page = book_sources[book_url]
        record = extract_raw_record(html, book_url, source_page)
        raw_records.append(record)
        if not from_cache:
            print(f"  [{i:02d}] FETCH {book_url}")
        else:
            print(f"  [{i:02d}] cache {book_url}")

    print(f"detail_pages={len(raw_records)}")
    pretty = json.dumps(raw_records[0], indent=2, ensure_ascii=False)
    print("sample raw record:\n" + pretty)


if __name__ == "__main__":
    sys.exit(main())
