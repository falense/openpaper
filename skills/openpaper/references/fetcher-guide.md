# Fetcher Guide

How to write a fetcher for a new news source.

---

## Architecture

A fetcher is a standalone Python script that retrieves article **listings** from a single source. The pipeline (`fetch_all.py`) runs fetchers in `--listing-only` mode, deduplicates centrally against `seen.txt`, then fetches content with a shared Playwright browser. Fetchers do NOT handle dedup or content fetching.

---

## File structure

```
.openpaper/sources/
  _base.py            # shared utilities (auto-deployed by fetch_all.py)
  hackernews.py
  bbc.py
```

The filename stem is the source slug (`anthropic_engineering.py` → `anthropic-engineering`).

---

## Interface contract

Every fetcher must:

1. Be a standalone Python script with **PEP 723 inline dependency metadata**
2. Accept `--cache-dir <path>` and `--listing-only` flags
3. Print a **JSON array of article objects** to stdout
4. Print errors to stderr
5. Exit 0 even on partial failures

### Article schema

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
  "discussion_url": null
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | str | yes | Article headline |
| `url` | str | yes | Canonical URL |
| `source` | str | yes | Must match filename stem |
| `summary` | str/null | no | Short summary |
| `date` | str/null | no | ISO 8601 |
| `author` | str/null | no | Byline |
| `content` | str/null | no | null in listing-only unless free from RSS body |
| `image_url` | str/null | no | og:image or twitter:image URL |
| `discussion_url` | str/null | no | Discussion thread link |

### `--listing-only` behavior

When set (the pipeline always passes it):

1. Fetch the listing (RSS, API, or listing page)
2. Output metadata — set `content` to null unless the listing provides it free (e.g., RSS `entry.content`)
3. Do NOT launch Playwright for individual articles
4. Do NOT deduplicate

---

## Using `_base.py`

Import from `_base` for shared utilities. The canonical copy lives at `scripts/fetcher_base.py` and is auto-deployed by `fetch_all.py`.

Available:
- **`run_rss_fetcher(source_name, feed_url, **kwargs)`** — complete RSS/Atom fetcher template
- **`run_html_fetcher(source_name, listing_url, parse_listing, **kwargs)`** — complete HTML scraper template
- Utilities: `cache_key`, `is_fresh`, `read_cache`, `write_cache`, `fetch_page`, `extract_text`, `extract_image`, `detect_paywall`, `parse_args`, `output_articles`, `fetch_feed`, `parse_date`

### RSS fetcher example

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["feedparser>=6.0", "playwright>=1.40", "beautifulsoup4>=4.12"]
# ///
from _base import run_rss_fetcher

if __name__ == "__main__":
    run_rss_fetcher(
        source_name="bbc",
        feed_url="https://feeds.bbci.co.uk/news/rss.xml",
        url_filter=lambda url: "/live/" not in url,
        has_paywall=True,
    )
```

`run_rss_fetcher` kwargs: `url_filter`, `url_transform`, `has_paywall`, `use_rss_content`, `extra_paywall_phrases`, `fetch_delay` (default 0.5), `max_entries` (default 50).

### HTML scraper example

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.40", "beautifulsoup4>=4.12"]
# ///
from _base import run_html_fetcher
from bs4 import BeautifulSoup

def parse_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for el in soup.select("article"):
        link = el.find("a", href=True)
        if not link:
            continue
        title_tag = el.find(["h2", "h3", "h1"])
        items.append({
            "url": link["href"],
            "title": title_tag.get_text(strip=True) if title_tag else "Untitled",
        })
    return items

if __name__ == "__main__":
    run_html_fetcher(
        source_name="example",
        listing_url="https://example.com/news",
        parse_listing=parse_listing,
    )
```

`run_html_fetcher` kwargs: `has_paywall`, `extra_paywall_phrases`, `fetch_delay`, `max_items`.

### Custom fetcher (e.g., JSON API)

For unique sources like Hacker News's Firebase API, import individual utilities from `_base` and write a custom `main()` using `parse_args()` and `output_articles()`.

---

## Source type strategy

| Tier | Listing method | When to use | Dependencies |
|------|----------------|-------------|-------------|
| **RSS** | `feedparser` + `urllib.request` | Source has RSS/Atom feed (preferred) | `feedparser` |
| **Playwright** | Headless Chromium | No feed/API; JS-rendered pages | `playwright` |
| **API** | `httpx` | Machine-readable JSON/XML API only | `httpx` |

**Never use httpx for web pages** — use Playwright for all web content.

---

## Error handling

- Wrap each article in try/except — never let one bad article kill the batch
- Always exit 0 (the pipeline checks stdout for the JSON array)
- All logging to stderr; stdout is exclusively for JSON output

---

## Checklist

- [ ] PEP 723 metadata lists all dependencies
- [ ] `--cache-dir` and `--listing-only` flags work
- [ ] `--listing-only` outputs metadata without Playwright content fetching
- [ ] Output is a valid JSON array on stdout, errors to stderr
- [ ] Each article has `title`, `url`, and `source`
- [ ] `source` matches filename stem
- [ ] Per-article exceptions caught; exit 0 on partial failures
