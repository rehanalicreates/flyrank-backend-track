"""
Stage 1: fetch and cache HTML.

Downloads the first catalogue page once (with an honest user-agent, a timeout,
and a status check), saves it to cache/, and reads from cache on later runs.
"""
import os
import sys
import time

import requests

BASE_URL = "https://books.toscrape.com/"
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")

USER_AGENT = (
    "FlyRankInternship-A9/1.0 "
    "(polite scraper; repo: https://github.com/rehanalicreates/flyrank-backend-track)"
)
TIMEOUT = 10  # seconds; give up, never wait forever


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


def main() -> None:
    html, from_cache = fetch_page(
        BASE_URL + "catalogue/page-1.html", "catalogue-page-1.html"
    )
    mode = "CACHE HIT" if from_cache else "FETCH"
    print(f"{mode}  size={len(html)} bytes  url={BASE_URL}catalogue/page-1.html")


if __name__ == "__main__":
    sys.exit(main())
