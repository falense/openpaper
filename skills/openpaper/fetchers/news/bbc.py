#!/usr/bin/env python3
"""Fetch articles from BBC News (RSS)."""
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "feedparser>=6.0",
#     "playwright>=1.40",
#     "beautifulsoup4>=4.12",
# ]
# ///

from _base import run_rss_fetcher

if __name__ == "__main__":
    run_rss_fetcher(
        source_name="bbc",
        feed_url="https://feeds.bbci.co.uk/news/rss.xml",
        # Skip live blogs and video pages — not readable as articles.
        url_filter=lambda url: "/live/" not in url and "/av/" not in url,
        has_paywall=False,
    )
