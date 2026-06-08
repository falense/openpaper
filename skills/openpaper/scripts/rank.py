# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""OpenPaper deterministic ranker for the Claude `ranking: deterministic` flow.

In Claude mode the agent normally curates by hand. With `ranking: deterministic`
in config.yaml, the agent instead delegates *selection* to the same arithmetic
the local engine uses (`curation_core`), so the slate and role tiers are
reproducible and obey the topic/source/serendipity caps from
`references/curation-guide.md` — no freehand drift. The agent still supplies the
semantic relevance scores (Claude-quality judgement) and writes the summaries.

Two steps the agent runs:

  1. Discover what to score against and the caps in play:
         uv run rank.py --data-dir .openpaper --print-prefs
     -> JSON: {interests, source_priority, max_articles, reading_minutes, caps,
               articles:[{slug, source, title, date, url, has_image}]}

  2. After scoring every article 0-1 against each interest, feed the scores back:
         uv run rank.py --data-dir .openpaper --match-scores scores.json
     (or pipe the JSON on stdin with `--match-scores -`)
     -> JSON: the ordered edition plan, one entry per selected article:
        [{slug, source, title, url, image_url, role, score, primary_topic, match}]

`scores.json` maps slug -> {interest_name: 0.0-1.0, ...}. Interest names must match
those from --print-prefs. Articles with no entry default to all-zero (dropped).

The agent then writes role-calibrated summaries for the returned slate and
assembles the edition YAML exactly as in the normal Claude flow — optionally
overriding the lead or swapping a story using editorial judgement the arithmetic
can't capture (cross-source dedup, a thin source, a more interesting angle).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

from curation_core import (
    Article, load_config, load_incoming, parse_preferences, score, select_plan,
)


def print_prefs(data_dir: Path) -> dict:
    prefs = parse_preferences((data_dir / "preferences.md").read_text())
    arts = load_incoming(data_dir)
    n = prefs.max_articles
    return {
        "interests": prefs.interests,
        "source_priority": prefs.source_priority,
        "max_articles": n,
        "reading_minutes": prefs.reading_minutes,
        "caps": {
            "per_topic": math.ceil(0.3 * n),
            "per_source": max(1, math.floor(0.4 * n)),
            "serendipity_min": math.ceil(0.2 * n),
        },
        "articles": [
            {
                "slug": a.slug, "source": a.source, "title": a.title,
                "date": a.date.isoformat() if a.date else None,
                "url": a.url, "has_image": bool(a.image_url),
            }
            for a in arts
        ],
    }


def rank(data_dir: Path, scores: dict[str, dict], today: dt.date) -> list[dict]:
    prefs = parse_preferences((data_dir / "preferences.md").read_text())
    arts = load_incoming(data_dir)
    if not arts:
        sys.exit("Error: no articles in incoming/. Run fetch_all.py first.")

    interests = list(prefs.interests)
    for a in arts:
        raw = scores.get(a.slug, {})
        a.match = {k: max(0.0, min(1.0, float(raw.get(k, 0.0) or 0.0))) for k in interests}
        a.score = score(a, prefs, today)

    plan = select_plan(arts, prefs, today)
    return [
        {
            "slug": a.slug, "source": a.source, "title": a.title,
            "url": a.url, "image_url": a.image_url,
            "role": a.role, "score": a.score, "primary_topic": a.primary_topic,
            "match": a.match,
        }
        for a in plan
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="OpenPaper deterministic ranker (Claude flow)")
    ap.add_argument("--data-dir", type=Path, default=Path(".openpaper"))
    ap.add_argument("--print-prefs", action="store_true",
                    help="emit interests, caps and the article list to score against")
    ap.add_argument("--match-scores", metavar="PATH",
                    help="JSON file (slug -> {interest: 0-1}); '-' to read stdin")
    ap.add_argument("--today", help="YYYY-MM-DD override for reproducible ranking")
    args = ap.parse_args()

    data_dir = args.data_dir.resolve()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    if args.print_prefs:
        json.dump(print_prefs(data_dir), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    if not args.match_scores:
        ap.error("provide --match-scores PATH (or '-' for stdin), or use --print-prefs")

    raw = sys.stdin.read() if args.match_scores == "-" else Path(args.match_scores).read_text()
    scores = json.loads(raw)
    plan = rank(data_dir, scores, today)
    json.dump(plan, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
