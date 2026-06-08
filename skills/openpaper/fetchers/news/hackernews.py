#!/usr/bin/env python3
"""Fetch top stories from Hacker News via the Firebase API.

Listing comes from the public HN Firebase API (machine-readable JSON, so httpx
is appropriate here). Article content is fetched centrally by the pipeline.
"""
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "playwright>=1.40",
#     "beautifulsoup4>=4.12",
# ]
# ///

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import httpx

from _base import (
    LISTING_TTL,
    is_fresh,
    output_articles,
    parse_args,
)

SOURCE_NAME = "hackernews"
TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
HN_ITEM_PAGE = "https://news.ycombinator.com/item?id={id}"
MAX_STORIES = 30
MIN_SCORE = 30  # filter out low-signal noise


def _cached_json(cache_dir, key: str, fetch_fn):
    """Read JSON from cache if fresh, else fetch and cache it."""
    if cache_dir:
        path = cache_dir / f"{key}.json"
        if is_fresh(path, LISTING_TTL):
            return json.loads(path.read_text(encoding="utf-8"))
    data = fetch_fn()
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{key}.json").write_text(
            json.dumps(data), encoding="utf-8",
        )
    return data


def main() -> None:
    args = parse_args()
    cache_dir = args.cache_dir

    try:
        with httpx.Client(
            timeout=30, headers={"User-Agent": "OpenPaper/1.0"},
        ) as client:
            top_ids = _cached_json(
                cache_dir, "topstories",
                lambda: client.get(TOP_STORIES_URL).json(),
            )

            articles = []
            for item_id in top_ids[: MAX_STORIES * 2]:
                if len(articles) >= MAX_STORIES:
                    break
                try:
                    item = _cached_json(
                        cache_dir, f"item-{item_id}",
                        lambda i=item_id: client.get(
                            ITEM_URL.format(id=i),
                        ).json(),
                    )
                except Exception as exc:
                    print(f"[{SOURCE_NAME}] item {item_id} failed: {exc}",
                          file=sys.stderr)
                    continue

                if not item or item.get("type") != "story":
                    continue
                if item.get("dead") or item.get("deleted"):
                    continue
                if item.get("score", 0) < MIN_SCORE:
                    continue

                title = item.get("title", "Untitled")
                discussion = HN_ITEM_PAGE.format(id=item_id)
                # Self-posts (Ask/Show HN with no external link) point at HN.
                url = item.get("url") or discussion

                date = None
                if item.get("time"):
                    date = datetime.fromtimestamp(
                        item["time"], tz=timezone.utc,
                    ).isoformat()

                articles.append({
                    "title": title,
                    "url": url,
                    "source": SOURCE_NAME,
                    "summary": f"{item.get('score', 0)} points, "
                               f"{item.get('descendants', 0)} comments on Hacker News",
                    "date": date,
                    "author": item.get("by"),
                    "content": None,
                    "image_url": None,
                    "discussion_url": discussion,
                })
    except Exception as exc:
        print(f"[{SOURCE_NAME}] Failed: {exc}", file=sys.stderr)
        output_articles([])
        return

    print(f"[{SOURCE_NAME}] {len(articles)} article(s) in listing", file=sys.stderr)
    output_articles(articles)


if __name__ == "__main__":
    main()
