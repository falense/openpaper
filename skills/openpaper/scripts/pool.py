# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Chainable CLI for inspecting the OpenPaper incoming article pool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_DATA_DIR = ".openpaper"


def load_articles(incoming_dir: Path) -> list[dict]:
    articles = []
    if not incoming_dir.is_dir():
        return articles
    for p in sorted(incoming_dir.glob("*.json")):
        try:
            article = json.loads(p.read_text(encoding="utf-8"))
            article["_slug"] = p.stem
            articles.append(article)
        except (json.JSONDecodeError, OSError):
            print(f"warning: skipping {p.name}", file=sys.stderr)
    return articles


def word_count(article: dict) -> int:
    content = article.get("content") or ""
    return len(content.split())


def slug(article: dict) -> str:
    return article.get("_slug", "")


def has_image(article: dict) -> bool:
    return bool(article.get("image_url"))


def points(article: dict) -> int:
    summary = article.get("summary") or ""
    for part in summary.split("|"):
        part = part.strip().lower()
        if "score:" in part:
            try:
                return int(part.split(":", 1)[1].strip())
            except ValueError:
                pass
        for suffix in (" pts", " points"):
            if part.endswith(suffix):
                try:
                    return int(part[: -len(suffix)].strip())
                except ValueError:
                    pass
    return 0


def apply_filters(articles: list[dict], args: argparse.Namespace) -> list[dict]:
    if getattr(args, "source", None):
        articles = [a for a in articles if a.get("source") == args.source]
    if getattr(args, "has_image", False):
        articles = [a for a in articles if has_image(a)]
    return articles


SORT_KEYS = {
    "title": lambda a: (a.get("title") or "").lower(),
    "source": lambda a: (a.get("source") or "", (a.get("title") or "").lower()),
    "words": lambda a: -word_count(a),
    "points": lambda a: -points(a),
}


def apply_sort(articles: list[dict], sort_key: str) -> list[dict]:
    return sorted(articles, key=SORT_KEYS[sort_key])


def apply_limit(articles: list[dict], limit: int | None) -> list[dict]:
    if limit is not None:
        return articles[:limit]
    return articles


# ── Commands ──────────────────────────────────────────────────────────


def cmd_stats(articles: list[dict], args: argparse.Namespace) -> None:
    sources: dict[str, int] = {}
    with_images = 0
    total_words = 0
    for a in articles:
        src = a.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
        if has_image(a):
            with_images += 1
        total_words += word_count(a)

    if args.json:
        json.dump(
            {
                "sources": len(sources),
                "articles": len(articles),
                "with_images": with_images,
                "total_words": total_words,
                "by_source": sources,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        print(f"{len(sources)} sources, {len(articles)} articles, {with_images} with images, {total_words} total words")
        for src in sorted(sources):
            print(f"  {src}: {sources[src]}")


def cmd_list(articles: list[dict], args: argparse.Namespace) -> None:
    articles = apply_filters(articles, args)
    articles = apply_sort(articles, args.sort)
    articles = apply_limit(articles, args.limit)

    if not articles:
        print("no articles found", file=sys.stderr)
        sys.exit(1)

    if args.json:
        rows = []
        for a in articles:
            rows.append(
                {
                    "slug": slug(a),
                    "source": a.get("source", ""),
                    "title": a.get("title", ""),
                    "words": word_count(a),
                    "image": has_image(a),
                    "points": points(a),
                    "url": a.get("url", ""),
                }
            )
        json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        src_w = max((len(a.get("source", "")) for a in articles), default=6)
        src_w = max(src_w, 6)
        hdr = f"{'source':<{src_w}} | {'title':<50} | words | img"
        print(hdr)
        print("-" * len(hdr))
        for a in articles:
            src = a.get("source", "")
            title = a.get("title", "")
            if len(title) > 50:
                title = title[:47] + "..."
            wc = word_count(a)
            img = " ✓" if has_image(a) else "  "
            print(f"{src:<{src_w}} | {title:<50} | {wc:>5} | {img}")


def cmd_show(articles: list[dict], args: argparse.Namespace) -> None:
    by_slug = {}
    for a in articles:
        by_slug[slug(a)] = a

    found = []
    for s in args.slugs:
        if s in by_slug:
            found.append(by_slug[s])
        else:
            matches = [a for key, a in by_slug.items() if s in key]
            if len(matches) == 1:
                found.append(matches[0])
            elif len(matches) > 1:
                print(f"warning: '{s}' matches {len(matches)} articles, showing all", file=sys.stderr)
                found.extend(matches)
            else:
                print(f"warning: no article matching '{s}'", file=sys.stderr)

    if not found:
        print("no matching articles found", file=sys.stderr)
        sys.exit(1)

    if args.json:
        rows = []
        for a in found:
            rows.append(
                {
                    "slug": slug(a),
                    "source": a.get("source", ""),
                    "title": a.get("title", ""),
                    "url": a.get("url", ""),
                    "image_url": a.get("image_url"),
                    "author": a.get("author"),
                    "date": a.get("date"),
                    "words": word_count(a),
                    "content": a.get("content", ""),
                }
            )
        json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        for i, a in enumerate(found):
            if i > 0:
                print("\n" + "=" * 72 + "\n")
            print(f"Title:    {a.get('title', '')}")
            print(f"Source:   {a.get('source', '')}")
            print(f"URL:      {a.get('url', '')}")
            if a.get("image_url"):
                print(f"Image:    {a['image_url']}")
            if a.get("author"):
                print(f"Author:   {a['author']}")
            if a.get("date"):
                print(f"Date:     {a['date']}")
            print(f"Words:    {word_count(a)}")
            print()
            print(a.get("content", "(no content)"))


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pool.py",
        description="Inspect the OpenPaper incoming article pool.",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help=f"path to data directory (default: {DEFAULT_DATA_DIR})",
    )

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--json", action="store_true", help="machine-readable JSON output")

    sub = parser.add_subparsers(dest="command")

    # stats
    sub.add_parser("stats", parents=[shared], help="summary statistics")

    # list
    p_list = sub.add_parser("list", parents=[shared], help="one-line-per-article table")
    p_list.add_argument("--source", help="filter by source name")
    p_list.add_argument("--has-image", action="store_true", help="only articles with images")
    p_list.add_argument("--sort", choices=list(SORT_KEYS), default="source", help="sort order (default: source)")
    p_list.add_argument("--limit", type=int, help="max rows to show")

    # show
    p_show = sub.add_parser("show", parents=[shared], help="full content of selected articles")
    p_show.add_argument("slugs", nargs="+", help="article slug(s) or substring matches")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(2)

    incoming_dir = Path(args.data_dir) / "incoming"
    articles = load_articles(incoming_dir)

    if args.command == "stats":
        cmd_stats(articles, args)
    elif args.command == "list":
        cmd_list(articles, args)
    elif args.command == "show":
        cmd_show(articles, args)


if __name__ == "__main__":
    main()
