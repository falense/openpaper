# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40",
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Discover and run all OpenPaper news source fetchers.

Walks .openpaper/sources/, runs each fetcher in listing-only mode,
deduplicates articles against seen.txt, fetches content only for new
articles using a shared Playwright browser, and writes results to
.openpaper/incoming/.

Architecture aligned with TriOnyx newsagg: single centralized dedup,
content fetching after filtering, shared browser session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTENT_TTL = 86400
FETCH_DELAY = 0.5

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
    "les hele saken med vg+",
    "for å lese denne artikkelen",
    "logg inn for å lese",
]


# ---------------------------------------------------------------------------
# Content helpers (centralized — replaces per-fetcher copies)
# ---------------------------------------------------------------------------


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def is_fresh(path: Path, ttl: int) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < ttl


def detect_paywall(html: str, response_url: str, original_url: str) -> bool:
    lower_html = html.lower()

    for script in re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL,
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

    for phrase in TRUNCATION_PHRASES:
        if phrase in lower_html:
            return True

    for marker in ("/login", "/subscribe", "/register", "/signin"):
        if marker in response_url.lower() and marker not in original_url.lower():
            return True

    return False


def extract_text(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(
        ["nav", "footer", "aside", "script", "style", "noscript", "header", "form"]
    ):
        tag.decompose()
    for selector in [
        ".share", ".social", ".ad", ".ads", ".related", ".sidebar",
        ".comments", ".newsletter", ".popup", ".modal", ".cookie",
    ]:
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


def _fetch_page(browser, url: str) -> tuple[str, str]:
    """Fetch a page with Playwright. Returns (html, final_url)."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-")


def load_seen(seen_path: Path) -> set[str]:
    seen: set[str] = set()
    if seen_path.exists():
        for line in seen_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                seen.add(line)
    return seen


def append_seen(seen_path: Path, urls: list[str]) -> None:
    if not urls:
        return
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    with open(seen_path, "a", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------


def deploy_base_module(sources_dir: Path) -> None:
    """Copy fetcher_base.py to sources/_base.py so fetchers can import it."""
    canonical = Path(__file__).resolve().parent / "fetcher_base.py"
    target = sources_dir / "_base.py"
    if canonical.exists():
        shutil.copy2(canonical, target)


def discover_sources(sources_dir: Path) -> list[dict]:
    sources: list[dict] = []
    if not sources_dir.is_dir():
        return sources

    for child in sorted(sources_dir.glob("*.py")):
        if child.name.startswith("_"):
            continue
        name = child.stem.replace("_", "-")
        sources.append(
            {
                "name": name,
                "fetcher_path": child,
            }
        )
    return sources


# ---------------------------------------------------------------------------
# Fetcher execution (listing-only)
# ---------------------------------------------------------------------------


def run_fetcher(
    source: dict,
    cache_dir: Path,
    timeout_seconds: int = 120,
) -> tuple[str, list[dict], str | None]:
    name = source["name"]
    fetcher_path = source["fetcher_path"]
    source_cache_dir = cache_dir / name
    source_cache_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "uv", "run",
        str(fetcher_path),
        "--cache-dir", str(source_cache_dir),
        "--listing-only",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(fetcher_path.parent),
        )
    except subprocess.TimeoutExpired:
        return name, [], f"Timed out after {timeout_seconds}s"
    except Exception as exc:
        return name, [], str(exc)

    if result.returncode != 0:
        stderr_snippet = result.stderr.strip()[:500] if result.stderr else "(no stderr)"
        return name, [], f"Exit code {result.returncode}: {stderr_snippet}"

    stdout = result.stdout.strip()
    if not stdout:
        return name, [], None

    try:
        articles = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return name, [], f"Invalid JSON output: {exc}"

    if not isinstance(articles, list):
        return name, [], f"Expected JSON array, got {type(articles).__name__}"

    return name, articles, None


# ---------------------------------------------------------------------------
# Content fetching (centralized, shared browser)
# ---------------------------------------------------------------------------


def fetch_content_batch(
    articles: list[dict],
    cache_dir: Path,
    throttle: float = FETCH_DELAY,
) -> None:
    """Fetch article content for new articles, modifying them in-place.

    Checks HTML cache first, then launches a shared Playwright browser
    only for uncached articles (like TriOnyx's fetch_articles_batch).
    """
    needs_browser: list[dict] = []

    for article in articles:
        if article.get("content"):
            continue

        url = article["url"]
        source = article.get("source", "unknown")
        source_cache = cache_dir / source
        source_cache.mkdir(parents=True, exist_ok=True)
        html_path = source_cache / f"{cache_key(url)}.html"

        if is_fresh(html_path, CONTENT_TTL):
            html = html_path.read_text(encoding="utf-8")
            if detect_paywall(html, url, url):
                article["_paywalled"] = True
            else:
                article["content"] = extract_text(html)
                article["image_url"] = extract_image(html)
        else:
            needs_browser.append(article)

    if not needs_browser:
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()

        total = len(needs_browser)
        for i, article in enumerate(needs_browser):
            url = article["url"]
            source = article.get("source", "unknown")
            title = article.get("title", url)[:60]
            print(
                f"  [{i + 1}/{total}] [{source}] {title}",
                file=sys.stderr,
            )
            source_cache = cache_dir / source
            source_cache.mkdir(parents=True, exist_ok=True)

            try:
                html, final_url = _fetch_page(browser, url)
                (source_cache / f"{cache_key(url)}.html").write_text(
                    html, encoding="utf-8",
                )

                if detect_paywall(html, final_url, url):
                    article["_paywalled"] = True
                else:
                    article["content"] = extract_text(html)
                    article["image_url"] = extract_image(html)
            except Exception as exc:
                print(
                    f"[{source}] Content fetch failed: {url}: {exc}",
                    file=sys.stderr,
                )

            if i < len(needs_browser) - 1:
                time.sleep(throttle)

        browser.close()


# ---------------------------------------------------------------------------
# Article writing
# ---------------------------------------------------------------------------


def write_article(article: dict, incoming_dir: Path) -> Path | None:
    incoming_dir.mkdir(parents=True, exist_ok=True)

    title = article.get("title") or article.get("url", "untitled")
    slug = slugify(title)
    if not slug:
        slug = "untitled"

    path = incoming_dir / f"{slug}.json"

    if path.exists():
        return None

    path.write_text(
        json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def fetch_all(
    data_dir: Path,
    source_filter: str | None = None,
    parallel: int = 4,
) -> None:
    sources_dir = data_dir / "sources"
    cache_dir = data_dir / "cache"
    incoming_dir = data_dir / "incoming"
    seen_path = data_dir / "seen.txt"

    deploy_base_module(sources_dir)
    sources = discover_sources(sources_dir)
    if source_filter:
        sources = [s for s in sources if s["name"] == source_filter]
        if not sources:
            print(f"Error: source {source_filter!r} not found.", file=sys.stderr)
            sys.exit(1)

    if not sources:
        print("No sources found. Add sources to .openpaper/sources/.", file=sys.stderr)
        return

    seen = load_seen(seen_path)
    start = time.monotonic()

    # --- Phase 1: Run all fetchers in listing-only mode ---
    print(f"Fetching listings from {len(sources)} source(s)...", file=sys.stderr)
    all_articles: list[dict] = []
    total_errors = 0

    workers = min(parallel, len(sources))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_fetcher, src, cache_dir): src["name"]
            for src in sources
        }

        for future in as_completed(futures):
            name = futures[future]
            try:
                source_name, articles, error = future.result()
            except Exception as exc:
                print(f"[{name}] Unexpected error: {exc}", file=sys.stderr)
                total_errors += 1
                continue

            if error:
                print(f"[{name}] Error: {error}", file=sys.stderr)
                total_errors += 1
                continue

            print(
                f"[{source_name}] {len(articles)} article(s) in listing",
                file=sys.stderr,
            )
            all_articles.extend(articles)

    # --- Phase 2: Deduplicate against seen set ---
    new_articles: list[dict] = []
    for article in all_articles:
        url = article.get("url", "")
        if not url or url in seen:
            continue
        title = article.get("title") or url
        slug = slugify(title)
        if slug in seen:
            continue
        new_articles.append(article)
        seen.add(url)
        seen.add(slug)

    if not new_articles:
        elapsed = time.monotonic() - start
        print(
            f"\nDone in {elapsed:.1f}s: {len(sources)} source(s) checked, "
            f"0 new article(s), {total_errors} error(s).",
            file=sys.stderr,
        )
        return

    print(
        f"\n{len(new_articles)} new article(s) — fetching content...",
        file=sys.stderr,
    )

    # --- Phase 3: Fetch content for new articles (shared browser) ---
    fetch_content_batch(new_articles, cache_dir)

    # --- Phase 4: Write articles to incoming/ and update seen.txt ---
    written = 0
    all_urls = [a["url"] for a in new_articles]

    for article in new_articles:
        url = article["url"]
        source = article.get("source", "unknown")
        title = article.get("title", url)

        if article.pop("_paywalled", False):
            print(f"[{source}] Skipping (paywalled): {title}", file=sys.stderr)
            continue

        if not article.get("content"):
            print(f"[{source}] Skipping (no content): {title}", file=sys.stderr)
            continue

        path = write_article(article, incoming_dir)
        if path:
            written += 1

    append_seen(seen_path, all_urls)

    elapsed = time.monotonic() - start
    print(
        f"\nDone in {elapsed:.1f}s: {len(sources)} source(s) checked, "
        f"{written} new article(s), {total_errors} error(s).",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover and run all OpenPaper news source fetchers.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".openpaper"),
        help="Path to .openpaper/ data directory (default: .openpaper)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Fetch only a specific source by name",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Maximum number of parallel fetchers (default: 4)",
    )

    args = parser.parse_args()

    fetch_all(
        data_dir=args.data_dir.resolve(),
        source_filter=args.source,
        parallel=args.parallel,
    )


if __name__ == "__main__":
    main()
