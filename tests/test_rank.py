"""Unit tests for the deterministic ranker used by the Claude flow (rank.py).

These cover the engine-agnostic glue: feeding externally-supplied match scores
through the shared `curation_core` pipeline and emitting a plan. The arithmetic
itself is covered by test_curate.py.
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "openpaper" / "scripts"))

import rank as r  # noqa: E402
from curation_core import Article  # noqa: E402

TODAY = dt.date(2026, 6, 8)

PREFS = """\
# Prefs
## Interests
- Technology and AI (very interested)
- Norway (very interested)
- Climate (some interest)
## Sources
- Hacker News
- NRK
## Reading Profile
I like ~6 articles, about 10 minutes of reading.
"""


def _data_dir(tmp_path: Path) -> Path:
    (tmp_path / "incoming").mkdir()
    (tmp_path / "preferences.md").write_text(PREFS)
    articles = [
        ("ai-breakthrough", "Hacker News", "Big AI breakthrough", "2026-06-08"),
        ("ai-tooling", "Hacker News", "New AI dev tool", "2026-06-08"),
        ("oslo-budget", "NRK", "Oslo budget passes", "2026-06-08"),
        ("fjord-warm", "NRK", "Fjord hits record temperature", "2026-06-07"),
        ("sports-result", "NRK", "Football result", "2026-06-08"),
    ]
    for slug, src, title, date in articles:
        (tmp_path / "incoming" / f"{slug}.json").write_text(json.dumps(
            {"title": title, "source": src, "date": date, "url": f"https://x/{slug}",
             "content": title}))
    return tmp_path


def test_article_slug_strips_json():
    assert Article("t", "s", None, "", "", "", None, "oslo-budget.json").slug == "oslo-budget"


def test_print_prefs_reports_caps_and_pool(tmp_path):
    out = r.print_prefs(_data_dir(tmp_path))
    assert set(out["interests"]) == {"Technology and AI", "Norway", "Climate"}
    assert out["max_articles"] == 6
    assert out["caps"] == {"per_topic": 2, "per_source": 2, "serendipity_min": 2}
    assert {a["slug"] for a in out["articles"]} == {
        "ai-breakthrough", "ai-tooling", "oslo-budget", "fjord-warm", "sports-result"}


def test_rank_orders_and_assigns_roles(tmp_path):
    scores = {
        "ai-breakthrough": {"Technology and AI": 0.95},
        "ai-tooling": {"Technology and AI": 0.85},
        "oslo-budget": {"Norway": 0.9},
        "fjord-warm": {"Norway": 0.6, "Climate": 0.9},
        "sports-result": {"Norway": 0.5},
    }
    plan = r.rank(_data_dir(tmp_path), scores, TODAY)
    assert plan[0]["role"] == "lead"
    assert [p["role"] for p in plan].count("lead") == 1
    # Source cap is floor(0.4*6)=2, so NRK (3 candidates) is capped at 2.
    assert sum(p["source"] == "NRK" for p in plan) <= 2


def test_rank_missing_scores_default_to_zero(tmp_path):
    # Only one article scored; the unscored ones get all-zero match.
    plan = r.rank(_data_dir(tmp_path), {"ai-breakthrough": {"Technology and AI": 0.9}}, TODAY)
    scored = next(p for p in plan if p["slug"] == "ai-breakthrough")
    assert scored["match"] == {"Technology and AI": 0.9, "Norway": 0.0, "Climate": 0.0}
