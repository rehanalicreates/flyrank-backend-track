# The Polite Scraper

A small, polite scraping pipeline for **Books to Scrape** — collects the first three
catalogue pages, visits all 60 book pages, turns messy HTML into clean, checked JSON,
survives a broken page, and reports every run.

Lane: **Python** (requests + BeautifulSoup + Pydantic)

## Target classification

- **Site:** Books to Scrape (`https://books.toscrape.com`)
- **Why:** the site itself says so — the page banner reads *"This is a demo website for web
  scraping purposes. Prices and ratings here were randomly assigned and have no real
  meaning."* It is a public practice sandbox built exactly for this.
- **How much:** the first 3 catalogue pages only (60 books).
- **What data:** title, product URL, price, availability, rating, description, source page,
  fetch time.
- **Why appropriate:** it is a sandbox made for practice; the scope is tiny and fixed.

**Robots check:** `GET https://books.toscrape.com/robots.txt` returned **404 — no
robots file found**. A missing file is not permission, it is just a missing file; the
sandbox banner is the permission here, and the scope stays minimal either way.

## Politeness rules

- Honest user-agent naming us and linking this repo
- Timeout on every request (10 s) — never wait forever
- Status code checked before parsing; only 200 means "here is your page"
- At least 500 ms between real requests; cached pages cost nothing
- One retry on timeout / 5xx — never on 404 or 403
- One deliberately broken URL is tested on our side only, never against the real site

> **I will not reuse this code on another site without checking its rules and terms first.**

**Ethics note (in my own words):** use an official API when one exists; never bypass logins, paywalls,
or blocks; collect only what you need. This scraper touches nothing but the sandbox.

## Honest limitation

The cache is write-once by design: a page fetched today is served from `cache/` forever. If the site
changes its markup, delete `cache/` and rerun. The scope is deliberately fixed to the first three
catalogue pages — the pipeline does not follow beyond page 3 or paginate further.

## How to run

```sh
pip install -r requirements.txt
python src/main.py
```

Output: `output/books.json`, `output/errors.json`, `output/run-report.json`.
During development, requests are served from `cache/` — the site is asked once.

### Prove it survives a broken page

```sh
python src/main.py --test-broken-url
```

The run injects one deliberately nonexistent URL, logs the 404 in `run-report.json`
under `failures` (`books_failed: 1`), and every real book still gets scraped —
`books.json` stays at 60 records. The same path covers timeouts and 5xx, which get
one retry before being logged (404/403 are never retried).

## A stranger's evidence

Latest `output/run-report.json` (committed): `books_succeeded: 60`, `books_failed: 1`
(only the injected fake URL), `validation_errors: 0`, `cache_hits: 66` (3 discovery
passes over the catalogue + 60 detail pages — the site was asked once, reruns read the
cache; `pages_fetched_live: 0` on rerun). Since all pages are cached, reruns finish in
seconds and `books.json` never grows beyond the 60 unique books — each run is
idempotent by `product_url`.

## Output schema

| field | type | required | notes |
|---|---|---|---|
| `title` | str | yes | |
| `product_url` | str | yes | canonical identity, absolute https URL |
| `price_text` | str | yes | raw text kept alongside the clean value |
| `price_gbp` | float | yes | parsed from `price_text` |
| `availability_text` | str | yes | raw stock text |
| `rating_text` | str | yes | e.g. "Three" |
| `description` | str / null | no | null when the page has none |
| `source_page` | str | yes | provenance: which catalogue page |
| `fetched_at` | str | yes | ISO UTC timestamp, provenance |
| `stock_count` | int / null | no | parsed from availability, e.g. 22 |

No browser is needed for this assignment: the data is already in the HTML the server
sends, so a browser would only add cost.