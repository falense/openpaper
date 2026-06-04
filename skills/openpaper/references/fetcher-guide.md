# Fetcher Guide

How to write a fetcher for a new news source in OpenPaper.

---

## Overview

A fetcher is a standalone Python script that retrieves article **listings** from a single news source. Fetchers are deterministic — once written, they run without AI on every subsequent invocation. The agent's job is to analyze the source, write the fetcher once, and hand it off.

**Architecture:** The pipeline (`fetch_all.py`) runs fetchers in `--listing-only` mode to collect article metadata, deduplicates centrally against `seen.txt`, then fetches content only for new articles using a shared Playwright browser. Fetchers do NOT handle dedup — that's the pipeline's job.

---

## File structure

Each source is a single Python file in `.openpaper/sources/`:

```
.openpaper/sources/
  _base.py            # shared utilities (deployed by fetch_all.py)
  hackernews.py
  bbc.py
  nrk.py
  ...
```

The filename stem is the source's slug (lowercase, underscores for multi-word names like `anthropic_engineering.py` → source name `anthropic-engineering`).

New fetchers should import helpers from `_base` (the shared module). The canonical copy lives at `skills/openpaper/scripts/fetcher_base.py` and is deployed to `_base.py` by `fetch_all.py`.

---

## Fetcher interface contract

Every `fetcher.py` must:

1. Be a standalone Python script (shebang `#!/usr/bin/env python3`)
2. Use **PEP 723 inline dependency metadata** so `uv run` can resolve deps without a venv
3. Accept these CLI flags:
   - `--cache-dir <path>` — directory for HTTP caching (the pipeline provides this)
   - `--listing-only` — when set, output article metadata without fetching content (the pipeline always uses this flag; content is fetched centrally)
4. Print a **JSON array of article objects** to stdout
5. Print errors and diagnostics to stderr
6. Exit 0 even on partial failures (so the pipeline continues)

### Article schema

Each article in the output array must conform to this shape:

```json
{
  "title": "Article headline",
  "url": "https://example.com/article",
  "source": "hackernews",
  "summary": "One or two sentence summary",
  "date": "2026-06-04T14:30:00Z",
  "author": "Jane Doe",
  "content": null,
  "image_url": null,
  "discussion_url": "https://news.ycombinator.com/item?id=12345"
}
```

| Field            | Type           | Required | Notes                                      |
| ---------------- | -------------- | -------- | ------------------------------------------ |
| `title`          | `str`          | yes      | Article headline                           |
| `url`            | `str`          | yes      | Canonical URL of the article               |
| `source`         | `str`          | yes      | Must match the source filename stem        |
| `summary`        | `str \| null`  | no       | Short summary or deck                      |
| `date`           | `str \| null`  | no       | ISO 8601 datetime string                   |
| `author`         | `str \| null`  | no       | Byline                                     |
| `content`        | `str \| null`  | no       | Full article text — null in listing-only mode unless available for free (e.g. RSS body) |
| `image_url`      | `str \| null`  | no       | og:image or twitter:image URL from the page|
| `discussion_url` | `str \| null`  | no       | Link to discussion thread (HN, Reddit, etc)|

### `--listing-only` behavior

When `--listing-only` is passed (the pipeline always passes it):

1. Fetch the article listing (RSS feed, API, or Playwright listing page)
2. Output all articles with metadata (`title`, `url`, `source`, `summary`, `date`, `author`)
3. Set `content` to `null` — UNLESS the listing source itself provides content for free (e.g. RSS feeds with full `entry.content` bodies). If available without extra fetching, include it.
4. Set `image_url` to `null`
5. Do NOT launch Playwright for individual article pages
6. Do NOT deduplicate — the pipeline handles that centrally

When `--listing-only` is NOT passed (standalone mode), the fetcher should also fetch full article content via Playwright for direct use.

---

## Shared base module (`_base.py`)

New fetchers should import from `_base` rather than duplicating utility code. The base provides:

- **`run_rss_fetcher(source_name, feed_url, **kwargs)`** — complete template for RSS/Atom feed sources
- **`run_html_fetcher(source_name, listing_url, parse_listing, **kwargs)`** — complete template for HTML-scraped sources
- **Utilities**: `cache_key`, `is_fresh`, `read_cache`, `write_cache`, `fetch_page`, `extract_text`, `extract_image`, `detect_paywall`, `parse_args`, `output_articles`, `fetch_feed`, `parse_date`

For RSS sources, a fetcher can be as simple as:

```python
from _base import run_rss_fetcher

if __name__ == "__main__":
    run_rss_fetcher(
        source_name="bbc",
        feed_url="https://feeds.bbci.co.uk/news/rss.xml",
        url_filter=lambda url: "/live/" not in url,
        has_paywall=True,
    )
```

For HTML scrapers, provide a `parse_listing(html) -> list[dict]` function that extracts `{"url": ..., "title": ...}` dicts.

For unique sources (like Hacker News's Firebase API), import individual utilities from `_base` and write a custom `main()`.

---

## Strategy by source type

Pick the simplest approach that works. **Never use httpx to fetch web pages** — it gets blocked by many sites and can't render JS. Use RSS or Playwright for all web content, and reserve httpx only for machine-readable APIs.

### Listing discovery (how to find articles)

In order of preference:

#### 1. RSS/Atom feeds (preferred)

Use `feedparser` + `urllib.request` (stdlib) to fetch the XML. This is the most reliable and polite approach — feeds are designed for machine consumption.

**When to use:** The source publishes an RSS or Atom feed.

**Dependencies:** `feedparser`

**Feed fetching pattern:** Use `urllib.request` (not httpx) to download the XML:

```python
import urllib.request

def fetch_feed(cache_dir):
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "OpenPaper/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return feedparser.parse(body)
```

#### 2. JSON APIs

Use `httpx` to hit a documented (or reverse-engineered) JSON API.

**When to use:** The site has a public API (like Hacker News Firebase API) or the browser dev tools reveal a clean JSON endpoint.

**Dependencies:** `httpx`

#### 3. Playwright (HTML listing pages)

Use `playwright` with headless Chromium to render the listing page.

**When to use:** No feed or API available. Works for both static HTML and JS-rendered sites.

**Dependencies:** `playwright`

### Content fetching

Content fetching is handled **centrally by the pipeline** (`fetch_all.py`), not by individual fetchers. The pipeline uses Playwright with a shared browser session to fetch article pages for all new articles across all sources.

Fetchers only need to provide article URLs in their listing output. The pipeline handles:
- HTML caching (SHA-256 URL hash, 24-hour TTL)
- Paywall detection and filtering
- Content extraction (article text, og:image)
- Shared browser session (no redundant Chromium launches)

For **standalone mode** (running a fetcher without the pipeline), fetchers should include their own content-fetching code with the same patterns documented below.

### Three fetcher tiers

| Tier | Listing | Content (pipeline) | Example sources |
|------|---------|-------------------|-----------------|
| **RSS** | `feedparser` + `urllib.request` | Centralized Playwright | bbc, nrk, vg, openai, importai, thegradient |
| **Playwright** | Playwright (render listing page) | Centralized Playwright | anthropic, deepmind, kode24 |
| **API** | `httpx` (JSON API only) | Centralized Playwright | hackernews |

httpx is **only** acceptable for machine-readable API endpoints (JSON, XML APIs) — never for web pages.

---

## Caching pattern

Fetchers receive a `--cache-dir` path. Use it for **listing caches only**:

### Cache key

Hash the URL with SHA-256, take the first 16 hex characters:

```python
import hashlib

def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]
```

### Listing cache

Cache the listing source (RSS XML, API response, or listing page HTML):

```
<cache-dir>/<key>.xml     # RSS feed XML
<cache-dir>/<key>.json    # API response (e.g. HN top stories)
<cache-dir>/<key>.html    # Playwright listing page
```

### TTL rules

| Content type      | Default TTL |
| ----------------- | ----------- |
| Listing pages     | 1 hour      |

Article content caching (24-hour TTL) is handled by the pipeline, not by individual fetchers.

Check TTL by comparing the file's `mtime` against `time.time()`:

```python
import time
from pathlib import Path

def is_fresh(path: Path, ttl_seconds: int) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl_seconds
```

---

## Example fetcher: RSS source

A complete, working fetcher for an RSS feed. In `--listing-only` mode (used by the pipeline), it just parses the feed — no Playwright needed. In standalone mode, it fetches content too.

```python
#!/usr/bin/env python3
"""Fetch articles from an RSS/Atom feed."""
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "feedparser>=6.0",
#     "playwright>=1.40",
#     "beautifulsoup4>=4.12",
# ]
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import feedparser

SOURCE_NAME = "example-rss"
FEED_URL = "https://example.com/feed.xml"
LISTING_TTL = 3600
CONTENT_TTL = 86400
FETCH_DELAY = 0.3

PAYWALL_SELECTORS = [
    ".paywall", ".subscribe-wall", ".subscription-wall",
    "#paywall-overlay", "[data-paywall]", ".piano-offer",
    ".meter-wall", ".premium-wall", ".regwall",
]

TRUNCATION_PHRASES = [
    "subscribe to continue",
    "sign in to read the full",
    "this article is for subscribers",
    "create a free account to continue",
    "already a subscriber?",
    "to read the full story",
    "subscribe for full access",
    "this content is for members",
    "become a member to read",
    "log in to continue reading",
]


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def is_fresh(path: Path, ttl: int) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < ttl


def detect_paywall(html: str, response_url: str, original_url: str) -> bool:
    lower_html = html.lower()

    for script in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            ld = json.loads(script)
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                if isinstance(item, dict) and item.get("isAccessibleForFree") is False:
                    return True
        except (json.JSONDecodeError, TypeError):
            pass

    soup = BeautifulSoup(html, "html.parser")
    tier_tag = soup.find("meta", attrs={"name": "article:content_tier"}) or \
               soup.find("meta", property="article:content_tier")
    if tier_tag:
        tier = (tier_tag.get("content") or "").lower()
        if tier in ("metered", "locked", "premium"):
            return True

    for selector in PAYWALL_SELECTORS:
        if soup.select_one(selector):
            return True

    for phrase in TRUNCATION_PHRASES:
        if phrase in lower_html:
            return True

    for marker in ("/login", "/subscribe", "/register", "/signin"):
        if marker in response_url.lower() and marker not in original_url.lower():
            return True

    return False


def _fetch_page(browser, url: str) -> tuple[str, str]:
    """Fetch a single page. Returns (html, final_url)."""
    page = browser.new_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=20_000)
    except Exception:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            pass
    html = page.content()
    final_url = page.url
    page.close()
    return html, final_url


def fetch_feed(cache_dir: Path | None) -> feedparser.FeedParserDict:
    if cache_dir:
        cached = cache_dir / f"{cache_key(FEED_URL)}.xml"
        if is_fresh(cached, LISTING_TTL):
            return feedparser.parse(cached.read_text())

    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "OpenPaper/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{cache_key(FEED_URL)}.xml").write_text(body)

    return feedparser.parse(body)


def fetch_content(browser, url: str, cache_dir: Path | None) -> tuple[str | None, str | None, bool]:
    """Fetch article content. Used in standalone mode only (not by pipeline)."""
    if cache_dir:
        cached = cache_dir / f"{cache_key(url)}.html"
        if is_fresh(cached, CONTENT_TTL):
            html = cached.read_text()
            if detect_paywall(html, url, url):
                return None, None, True
            return extract_text(html), extract_image(html), False

    try:
        html, final_url = _fetch_page(browser, url)
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{cache_key(url)}.html").write_text(html)

        if detect_paywall(html, final_url, url):
            return None, None, True

        return extract_text(html), extract_image(html), False
    except Exception as exc:
        print(f"[{SOURCE_NAME}] Content fetch failed: {url}: {exc}", file=sys.stderr)
        return None, None, False


def extract_text(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["nav", "footer", "aside", "script", "style", "noscript", "header", "form"]):
        tag.decompose()
    for selector in [".share", ".social", ".ad", ".ads", ".related", ".sidebar",
                     ".comments", ".newsletter", ".popup", ".modal", ".cookie"]:
        for el in soup.select(selector):
            el.decompose()

    article = soup.find("article") or soup.find("main")
    if article:
        text = article.get_text(separator="\n", strip=True)
        if len(text) >= 100:
            return text

    blocks = soup.find_all(["div", "section"])
    if blocks:
        best = max(blocks, key=lambda b: len(b.get_text(strip=True)))
        text = best.get_text(separator="\n", strip=True)
        if len(text) >= 100:
            return text

    return None


def extract_image(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        if prop in ("og:image", "twitter:image"):
            url = meta.get("content", "").strip()
            if url and url.startswith("http"):
                return url
    return None


def parse_date(entry: feedparser.FeedParserDict) -> str | None:
    from email.utils import parsedate_to_datetime
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw).isoformat()
            except Exception:
                pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--listing-only", action="store_true")
    args = parser.parse_args()

    try:
        feed = fetch_feed(args.cache_dir)
    except Exception as exc:
        print(f"[{SOURCE_NAME}] Failed to fetch feed: {exc}", file=sys.stderr)
        json.dump([], sys.stdout)
        print(file=sys.stdout)
        return

    if args.listing_only:
        articles = []
        for entry in feed.entries:
            url = entry.get("link", "")
            if not url:
                continue

            title = entry.get("title", "Untitled")
            summary = entry.get("summary", None)
            if summary and "<" in summary:
                summary = BeautifulSoup(summary, "html.parser").get_text(strip=True)

            articles.append({
                "title": title,
                "url": url,
                "source": SOURCE_NAME,
                "summary": summary,
                "date": parse_date(entry),
                "author": entry.get("author", None),
                "content": None,
                "image_url": None,
                "discussion_url": None,
            })
        print(f"[{SOURCE_NAME}] {len(articles)} article(s) in listing", file=sys.stderr)
        json.dump(articles, sys.stdout, ensure_ascii=False, indent=2)
        print(file=sys.stdout)
        return

    # Standalone mode: fetch content with Playwright
    articles = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        for entry in feed.entries:
            url = entry.get("link", "")
            if not url:
                continue

            try:
                title = entry.get("title", "Untitled")

                content, image_url, is_paywalled = fetch_content(browser, url, args.cache_dir)
                if is_paywalled:
                    print(f"[{SOURCE_NAME}] Skipping (paywalled): {title}", file=sys.stderr)
                    continue

                summary = entry.get("summary", None)
                if summary and "<" in summary:
                    summary = BeautifulSoup(summary, "html.parser").get_text(strip=True)

                articles.append({
                    "title": title,
                    "url": url,
                    "source": SOURCE_NAME,
                    "summary": summary,
                    "date": parse_date(entry),
                    "author": entry.get("author", None),
                    "content": content,
                    "image_url": image_url,
                    "discussion_url": None,
                })

                time.sleep(FETCH_DELAY)

            except Exception as exc:
                print(f"[{SOURCE_NAME}] Skipping entry: {exc}", file=sys.stderr)
                continue

        browser.close()

    print(f"[{SOURCE_NAME}] Fetched {len(articles)} articles", file=sys.stderr)
    json.dump(articles, sys.stdout, ensure_ascii=False, indent=2)
    print(file=sys.stdout)


if __name__ == "__main__":
    main()
```

### How to adapt this example

1. Change `SOURCE_NAME` and `FEED_URL`
2. If the feed includes full content in the entry body, read it from `entry.content[0].value` in the `--listing-only` branch — the pipeline will skip content fetching for articles that already have content
3. If the source has discussion URLs (like Hacker News `comments` links), populate `discussion_url`
4. Adjust `extract_text()` if the site uses unusual markup (for standalone mode)

---

## Example fetcher: Playwright (JS-rendered site)

For sites where the article listing page is rendered client-side. The pipeline still handles content fetching — the fetcher only needs Playwright for the listing page.

```python
#!/usr/bin/env python3
"""Fetch articles from a JavaScript-rendered news site."""
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40",
#     "beautifulsoup4>=4.12",
# ]
# ///
# NOTE: Requires `playwright install chromium` to have been run once.

from __future__ import annotations

import argparse
import hashlib
import html as html_module
import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

SOURCE_NAME = "example-jssite"
LISTING_URL = "https://example.com/news"
BASE_URL = "https://example.com"
LISTING_TTL = 3600
CONTENT_TTL = 86400

PAYWALL_SELECTORS = [
    ".paywall", ".subscribe-wall", ".subscription-wall",
    "#paywall-overlay", "[data-paywall]", ".piano-offer",
    ".meter-wall", ".premium-wall", ".regwall",
]

TRUNCATION_PHRASES = [
    "subscribe to continue",
    "sign in to read the full",
    "this article is for subscribers",
    "create a free account to continue",
    "already a subscriber?",
    "to read the full story",
    "subscribe for full access",
    "this content is for members",
    "become a member to read",
    "log in to continue reading",
]


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def is_fresh(path: Path, ttl: int) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < ttl


def detect_paywall(html: str, response_url: str, original_url: str) -> bool:
    """Return True if the page shows signs of a paywall."""
    lower_html = html.lower()

    for script in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            ld = json.loads(script)
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                if isinstance(item, dict) and item.get("isAccessibleForFree") is False:
                    return True
        except (json.JSONDecodeError, TypeError):
            pass

    soup = BeautifulSoup(html, "html.parser")
    tier_tag = soup.find("meta", attrs={"name": "article:content_tier"}) or \
               soup.find("meta", property="article:content_tier")
    if tier_tag:
        tier = (tier_tag.get("content") or "").lower()
        if tier in ("metered", "locked", "premium"):
            return True

    for selector in PAYWALL_SELECTORS:
        if soup.select_one(selector):
            return True

    for phrase in TRUNCATION_PHRASES:
        if phrase in lower_html:
            return True

    for marker in ("/login", "/subscribe", "/register", "/signin"):
        if marker in response_url.lower() and marker not in original_url.lower():
            return True

    return False


def _fetch_page(browser, url: str) -> tuple[str, str]:
    """Fetch a single page. Returns (html, final_url)."""
    page = browser.new_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=20_000)
    except Exception:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            pass
    html = page.content()
    final_url = page.url
    page.close()
    return html, final_url


def fetch_listing(browser, cache_dir: Path | None) -> str:
    """Get the listing page HTML, cached if fresh."""
    if cache_dir:
        cached = cache_dir / f"{cache_key(LISTING_URL)}.html"
        if is_fresh(cached, LISTING_TTL):
            return cached.read_text()

    html, _ = _fetch_page(browser, LISTING_URL)

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{cache_key(LISTING_URL)}.html").write_text(html)

    return html


def parse_listing(html: str) -> list[dict]:
    """Extract article links and metadata from the listing page."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Adapt these selectors to the target site
    for el in soup.select("article"):
        link_tag = el.find("a", href=True)
        if not link_tag:
            continue

        url = link_tag["href"]
        if url.startswith("/"):
            from urllib.parse import urljoin
            url = urljoin(LISTING_URL, url)

        title_tag = el.find(["h2", "h3", "h1"])
        title = title_tag.get_text(strip=True) if title_tag else "Untitled"

        summary_tag = el.find("p")
        summary = summary_tag.get_text(strip=True) if summary_tag else None

        items.append({
            "url": url,
            "title": title,
            "summary": summary,
        })

    return items


def fetch_content(browser, url: str, cache_dir: Path | None) -> tuple[str | None, str | None, bool]:
    """Fetch article content. Used in standalone mode only (not by pipeline)."""
    if cache_dir:
        cached = cache_dir / f"{cache_key(url)}.html"
        if is_fresh(cached, CONTENT_TTL):
            html = cached.read_text()
            if detect_paywall(html, url, url):
                return None, None, True
            return extract_text(html), extract_image(html), False

    try:
        html, final_url = _fetch_page(browser, url)

        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{cache_key(url)}.html").write_text(html)

        if detect_paywall(html, final_url, url):
            return None, None, True

        return extract_text(html), extract_image(html), False
    except Exception as exc:
        print(f"[{SOURCE_NAME}] Content fetch failed: {url}: {exc}", file=sys.stderr)
        return None, None, False


def extract_text(html: str) -> str | None:
    """Pull main article text from rendered HTML."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["nav", "footer", "aside", "script", "style", "noscript",
                               "header", "form"]):
        tag.decompose()

    for selector in [".share", ".social", ".ad", ".related", ".sidebar", ".comments"]:
        for el in soup.select(selector):
            el.decompose()

    article = soup.find("article") or soup.find("main")
    if article:
        text = article.get_text(separator="\n", strip=True)
        if len(text) >= 100:
            return text

    blocks = soup.find_all(["div", "section"])
    if blocks:
        best = max(blocks, key=lambda b: len(b.get_text(strip=True)))
        text = best.get_text(separator="\n", strip=True)
        if len(text) >= 100:
            return text

    return None


def extract_image(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        if prop in ("og:image", "twitter:image"):
            url = meta.get("content", "").strip()
            if url and url.startswith("http"):
                return url
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--listing-only", action="store_true")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()

        try:
            listing_html = fetch_listing(browser, args.cache_dir)
        except Exception as exc:
            print(f"[{SOURCE_NAME}] Failed to fetch listing: {exc}", file=sys.stderr)
            json.dump([], sys.stdout)
            print(file=sys.stdout)
            browser.close()
            return

        listing = parse_listing(listing_html)
        articles = []

        if args.listing_only:
            for item in listing:
                articles.append({
                    "title": item["title"],
                    "url": item["url"],
                    "source": SOURCE_NAME,
                    "summary": item.get("summary"),
                    "date": None,
                    "author": None,
                    "content": None,
                    "image_url": None,
                    "discussion_url": None,
                })
        else:
            for item in listing:
                url = item["url"]
                title = item["title"]
                try:
                    content, image_url, is_paywalled = fetch_content(browser, url, args.cache_dir)
                    if is_paywalled or content is None:
                        print(f"[{SOURCE_NAME}] Skipping (paywalled): {title}", file=sys.stderr)
                        continue
                    articles.append({
                        "title": title,
                        "url": url,
                        "source": SOURCE_NAME,
                        "summary": item.get("summary"),
                        "date": None,
                        "author": None,
                        "content": content,
                        "image_url": image_url,
                        "discussion_url": None,
                    })
                except Exception as exc:
                    print(f"[{SOURCE_NAME}] Skipping: {title}: {exc}", file=sys.stderr)
                    continue

        browser.close()

    print(f"[{SOURCE_NAME}] {len(articles)} article(s)", file=sys.stderr)
    json.dump(articles, sys.stdout, ensure_ascii=False, indent=2)
    print(file=sys.stdout)


if __name__ == "__main__":
    main()
```

### Key differences from the RSS example

- Uses `playwright.sync_api` instead of `feedparser`/`httpx`
- Launches a real browser even in listing-only mode (needed for JS-rendered listing pages)
- The `wait_selector` parameter is critical: you must identify a CSS selector that appears only after the JS framework has finished rendering

### When to use Playwright vs. httpx

Quick test: run `curl -s <URL> | grep -c '<article'` in a terminal. If you see 0 matches but the browser shows articles, the site is JS-rendered and needs Playwright.

---

## Error handling

### Per-article isolation

Never let one bad article kill the batch. Wrap each article's processing in a try/except:

```python
for entry in entries:
    try:
        article = process(entry)
        articles.append(article)
    except Exception as exc:
        print(f"[{SOURCE_NAME}] Skipping: {exc}", file=sys.stderr)
        continue
```

### Exit code

Always exit 0, even if some articles failed. The pipeline checks stdout for the JSON array. If the array is empty, the pipeline knows the source had a bad day.

Only exit non-zero for truly unrecoverable errors (bad arguments, missing dependencies).

### Stderr for diagnostics

All logging, warnings, and errors go to stderr. Stdout is reserved exclusively for the JSON output.

```python
# Good
print(f"[{SOURCE_NAME}] Fetched {len(articles)} articles", file=sys.stderr)

# Bad -- this corrupts the JSON output
print(f"Fetched {len(articles)} articles")
```

---

## Content extraction tips

These apply to the pipeline's centralized extraction and to standalone-mode content fetching.

### Stripping noise

Remove these elements before extracting text:

```python
NOISE_TAGS = ["nav", "footer", "aside", "script", "style", "noscript", "header", "form"]
NOISE_CLASSES = [".share", ".social", ".ad", ".ads", ".related", ".sidebar",
                 ".comments", ".newsletter", ".popup", ".modal", ".cookie"]
```

### Extraction priority

1. Look for `<article>` tag first — most semantic and reliable
2. Fall back to `<main>` tag
3. Fall back to the `<div>` or `<section>` with the most text content
4. If nothing works, return `None` (the article will still appear in the edition with just its title and summary)

### Minimum content length

Require at least 100 characters of extracted text. Anything shorter is likely a navigation fragment or error page, not real article content.

### Common gotchas

- **Paywalled content:** Paywalled articles are detected and excluded by the pipeline. The pipeline checks Schema.org `isAccessibleForFree`, meta `article:content_tier`, CSS selectors, truncation phrases, and login redirects.
- **Redirects to login pages:** The pipeline captures the final URL after redirects and compares it to the original URL to detect login/subscribe redirects.
- **Encoding issues:** Always use the response's declared encoding. For Playwright, `page.content()` returns decoded unicode.
- **Rate limiting:** The pipeline throttles content fetches with a configurable delay between requests.

---

## Paywall detection

Paywall detection is handled centrally by the pipeline's `fetch_all.py`. It checks:

1. **Schema.org `isAccessibleForFree`** in `<script type="application/ld+json">` blocks
2. **Meta tag `article:content_tier`** with values "metered", "locked", or "premium"
3. **CSS selector matching** against known paywall element selectors
4. **Truncation phrases** in the page HTML (e.g. "subscribe to continue")
5. **Login/subscribe redirect** detection by comparing the response URL to the original URL

Fetchers do NOT need to implement paywall detection for the pipeline path. The standalone mode should include its own copy for direct use.

---

## Running a fetcher

The pipeline invokes fetchers via `uv run`:

```bash
# Pipeline mode (listing only — fast, no content fetching)
uv run .openpaper/sources/hackernews.py \
  --cache-dir .openpaper/cache/hackernews \
  --listing-only

# Standalone mode (full fetch with content)
uv run .openpaper/sources/hackernews.py \
  --cache-dir .openpaper/cache/hackernews
```

`uv run` reads the PEP 723 metadata and installs dependencies into an ephemeral venv automatically. No manual setup required.

---

## Checklist for writing a new fetcher

Before considering a fetcher complete, verify:

- [ ] `config.yaml` exists with all required fields
- [ ] PEP 723 inline metadata lists all dependencies
- [ ] `--cache-dir` and `--listing-only` flags are implemented
- [ ] `--listing-only` mode outputs metadata without launching Playwright for content (RSS/API fetchers should not need Playwright at all in this mode)
- [ ] Output is a valid JSON array on stdout
- [ ] All errors go to stderr
- [ ] Each article has at least `title`, `url`, and `source`
- [ ] `source` field matches the directory name and `config.yaml` name
- [ ] Dates are ISO 8601 when present
- [ ] Per-article exceptions are caught (partial results returned)
- [ ] Exit code is 0 on partial failures
- [ ] The fetcher runs successfully via `uv run fetcher.py --cache-dir /tmp/test --listing-only`
