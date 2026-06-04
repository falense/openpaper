"""Shared utilities and templates for OpenPaper fetcher scripts.

This module is the canonical copy. fetch_all.py deploys it to
.openpaper/sources/_base.py so fetchers can import it directly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

LISTING_TTL = 3600
CONTENT_TTL = 86400

PAYWALL_SELECTORS = [
    ".paywall", ".subscribe-wall", ".subscription-wall",
    "#paywall-overlay", "[data-paywall]", ".piano-offer",
    ".meter-wall", ".premium-wall", ".regwall",
]

PAYWALL_PHRASES = [
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


def read_cache(cache_dir: Path | None, url: str, ttl: int, ext: str = ".html") -> str | None:
    if not cache_dir:
        return None
    cached = cache_dir / f"{cache_key(url)}{ext}"
    if is_fresh(cached, ttl):
        return cached.read_text(encoding="utf-8")
    return None


def write_cache(cache_dir: Path | None, url: str, content: str, ext: str = ".html") -> None:
    if not cache_dir:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{cache_key(url)}{ext}").write_text(content, encoding="utf-8")


def fetch_page(browser, url: str) -> str:
    page = browser.new_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=20_000)
    except Exception:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            pass
    html = page.content()
    page.close()
    return html


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


def detect_paywall(html: str, response_url: str, original_url: str,
                   extra_phrases: list[str] | None = None) -> bool:
    lower_html = html.lower()

    for script in re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL,
    ):
        try:
            ld = json.loads(script)
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                if isinstance(item, dict) and item.get("isAccessibleForFree") is False:
                    return True
        except (json.JSONDecodeError, TypeError):
            pass

    soup = BeautifulSoup(html, "html.parser")
    tier_tag = (
        soup.find("meta", attrs={"name": "article:content_tier"})
        or soup.find("meta", property="article:content_tier")
    )
    if tier_tag:
        tier = (tier_tag.get("content") or "").lower()
        if tier in ("metered", "locked", "premium"):
            return True

    for selector in PAYWALL_SELECTORS:
        if soup.select_one(selector):
            return True

    phrases = PAYWALL_PHRASES + (extra_phrases or [])
    for phrase in phrases:
        if phrase in lower_html:
            return True

    for marker in ("/login", "/subscribe", "/register", "/signin"):
        if marker in response_url.lower() and marker not in original_url.lower():
            return True

    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--listing-only", action="store_true")
    return parser.parse_args()


def output_articles(articles: list[dict]) -> None:
    json.dump(articles, sys.stdout, ensure_ascii=False, indent=2)
    print(file=sys.stdout)


# ---------------------------------------------------------------------------
# RSS helpers
# ---------------------------------------------------------------------------


def fetch_feed(feed_url: str, cache_dir: Path | None):
    import feedparser

    cached = read_cache(cache_dir, feed_url, LISTING_TTL, ext=".xml")
    if cached is not None:
        return feedparser.parse(cached)

    req = urllib.request.Request(feed_url, headers={"User-Agent": "OpenPaper/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    write_cache(cache_dir, feed_url, body, ext=".xml")
    return feedparser.parse(body)


def parse_date(entry) -> str | None:
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw).isoformat()
            except Exception:
                pass
    return None


def _fetch_content(browser, url: str, source_name: str, cache_dir: Path | None,
                   has_paywall: bool = False,
                   extra_paywall_phrases: list[str] | None = None,
                   ) -> tuple[str | None, str | None, bool]:
    cached = read_cache(cache_dir, url, CONTENT_TTL)
    if cached is not None:
        if has_paywall and detect_paywall(cached, url, url, extra_paywall_phrases):
            return None, None, True
        return extract_text(cached), extract_image(cached), False

    try:
        html = fetch_page(browser, url)
        write_cache(cache_dir, url, html)
        if has_paywall and detect_paywall(html, url, url, extra_paywall_phrases):
            return None, None, True
        return extract_text(html), extract_image(html), False
    except Exception as exc:
        print(f"[{source_name}] Content fetch failed: {url}: {exc}", file=sys.stderr)
        return None, None, False


# ---------------------------------------------------------------------------
# Template: RSS fetcher
# ---------------------------------------------------------------------------


def run_rss_fetcher(
    source_name: str,
    feed_url: str,
    *,
    url_filter=None,
    url_transform=None,
    has_paywall: bool = False,
    use_rss_content: bool = False,
    extra_paywall_phrases: list[str] | None = None,
    fetch_delay: float = 0.5,
    max_entries: int = 50,
) -> None:
    args = parse_args()

    try:
        feed = fetch_feed(feed_url, args.cache_dir)
    except Exception as exc:
        print(f"[{source_name}] Failed to fetch feed: {exc}", file=sys.stderr)
        output_articles([])
        return

    entries = feed.entries[:max_entries]

    if args.listing_only:
        articles = []
        for entry in entries:
            url = entry.get("link", "")
            if not url:
                continue
            if url_transform:
                url = url_transform(url)
            if url_filter and not url_filter(url):
                continue

            title = entry.get("title", "Untitled")
            summary = entry.get("summary")
            if summary and "<" in summary:
                summary = BeautifulSoup(summary, "html.parser").get_text(strip=True)

            content = None
            if use_rss_content and hasattr(entry, "content") and entry.content:
                rss_html = entry.content[0].get("value", "")
                rss_text = BeautifulSoup(rss_html, "html.parser").get_text(
                    separator="\n", strip=True,
                )
                if rss_text and len(rss_text) >= 100:
                    content = rss_text

            articles.append({
                "title": title,
                "url": url,
                "source": source_name,
                "summary": summary,
                "date": parse_date(entry),
                "author": entry.get("author"),
                "content": content,
                "image_url": None,
                "discussion_url": None,
            })
        print(f"[{source_name}] {len(articles)} article(s) in listing", file=sys.stderr)
        output_articles(articles)
        return

    articles = []
    with sync_playwright() as p:
        browser = p.chromium.launch()

        for entry in entries:
            url = entry.get("link", "")
            if not url:
                continue
            if url_transform:
                url = url_transform(url)
            if url_filter and not url_filter(url):
                continue

            try:
                title = entry.get("title", "Untitled")

                rss_content = None
                if use_rss_content and hasattr(entry, "content") and entry.content:
                    rss_text = BeautifulSoup(
                        entry.content[0].get("value", ""), "html.parser",
                    ).get_text(separator="\n", strip=True)
                    if rss_text and len(rss_text) >= 100:
                        rss_content = rss_text

                if rss_content:
                    content = rss_content
                    image_url = None
                else:
                    content, image_url, is_paywalled = _fetch_content(
                        browser, url, source_name, args.cache_dir,
                        has_paywall, extra_paywall_phrases,
                    )
                    if is_paywalled:
                        print(f"[{source_name}] Skipping (paywalled): {title}", file=sys.stderr)
                        continue

                summary = entry.get("summary")
                if summary and "<" in summary:
                    summary = BeautifulSoup(summary, "html.parser").get_text(strip=True)

                articles.append({
                    "title": title,
                    "url": url,
                    "source": source_name,
                    "summary": summary,
                    "date": parse_date(entry),
                    "author": entry.get("author"),
                    "content": content,
                    "image_url": image_url,
                    "discussion_url": None,
                })
                time.sleep(fetch_delay)

            except Exception as exc:
                print(f"[{source_name}] Skipping entry: {exc}", file=sys.stderr)
                continue

        browser.close()

    print(f"[{source_name}] Fetched {len(articles)} articles", file=sys.stderr)
    output_articles(articles)


# ---------------------------------------------------------------------------
# Template: HTML scraper
# ---------------------------------------------------------------------------


def run_html_fetcher(
    source_name: str,
    listing_url: str,
    parse_listing,
    *,
    has_paywall: bool = False,
    extra_paywall_phrases: list[str] | None = None,
    fetch_delay: float = 0.5,
    max_items: int = 50,
) -> None:
    args = parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()

        cached = read_cache(args.cache_dir, listing_url, LISTING_TTL)
        if cached is not None:
            listing_html = cached
        else:
            try:
                listing_html = fetch_page(browser, listing_url)
                write_cache(args.cache_dir, listing_url, listing_html)
            except Exception as exc:
                print(f"[{source_name}] Failed to fetch listing: {exc}", file=sys.stderr)
                output_articles([])
                browser.close()
                return

        listing = parse_listing(listing_html)[:max_items]
        articles = []

        if args.listing_only:
            for item in listing:
                articles.append({
                    "title": item["title"],
                    "url": item["url"],
                    "source": source_name,
                    "summary": item.get("summary"),
                    "date": item.get("date"),
                    "author": item.get("author"),
                    "content": None,
                    "image_url": None,
                    "discussion_url": None,
                })
        else:
            for item in listing:
                url = item["url"]
                title = item["title"]
                try:
                    content, image_url, is_paywalled = _fetch_content(
                        browser, url, source_name, args.cache_dir,
                        has_paywall, extra_paywall_phrases,
                    )
                    if is_paywalled:
                        print(f"[{source_name}] Skipping (paywalled): {title}", file=sys.stderr)
                        continue
                    articles.append({
                        "title": title,
                        "url": url,
                        "source": source_name,
                        "summary": item.get("summary"),
                        "date": item.get("date"),
                        "author": item.get("author"),
                        "content": content,
                        "image_url": image_url,
                        "discussion_url": None,
                    })
                    time.sleep(fetch_delay)
                except Exception as exc:
                    print(f"[{source_name}] Skipping: {title}: {exc}", file=sys.stderr)
                    continue

        browser.close()

    print(f"[{source_name}] {len(articles)} article(s)", file=sys.stderr)
    output_articles(articles)
