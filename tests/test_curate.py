"""Unit tests for the deterministic parts of the local curation engine.

These cover everything the local engine does WITHOUT a model — preference
parsing and the editorial scoring/selection arithmetic from curation-guide.md.
The model layer (semantic_match / summarise) is intentionally not exercised here.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "openpaper" / "scripts"))

import curate as c  # noqa: E402

TODAY = dt.date(2026, 6, 5)

SAMPLE_PREFS = """\
# My Reading Preferences

## Interests
- Technology and AI (very interested) — AI/ML, startups
- Open-source (interested)
- Climate (some interest) — environment
- World politics (passing interest)

## Sources
- Hacker News — primary tech source
- Ars Technica
- NRK — Norwegian national news

## Reading Profile
I like ~12 articles, about 18 minutes of reading.
Write the whole paper in Norwegian (bokmål).

## Feedback
- 2026-06-01: "AI policy update" — more like this.
- 2026-05-01: "Crypto speculation" — hide.
"""


def make(title, source, topic, match=None, date=TODAY):
    a = c.Article(title=title, source=source, date=date, summary="", content="",
                  url=f"https://x/{title}", image_url=None, file=f"{title}.json")
    a.match = match or {topic: 0.8}
    a.primary_topic = topic
    return a


# --------------------------------------------------------------- preferences
def test_parse_interests_weights():
    p = c.parse_preferences(SAMPLE_PREFS)
    assert p.interests["Technology and AI"] == 0.9
    assert p.interests["Open-source"] == 0.7          # hyphenated name preserved
    assert p.interests["Climate"] == 0.5
    assert p.interests["World politics"] == 0.3


def test_parse_sources_and_profile():
    p = c.parse_preferences(SAMPLE_PREFS)
    assert p.source_priority == ["hackernews", "arstechnica", "nrk"]
    assert p.max_articles == 12
    assert p.reading_minutes == 18
    assert "bokmål" in p.reading_profile


def test_parse_feedback():
    p = c.parse_preferences(SAMPLE_PREFS)
    assert [f["signal"] for f in p.feedback] == ["more", "hide"]


# --------------------------------------------------------------- bonuses
def test_source_bonus_by_position():
    pri = ["hackernews", "arstechnica", "nrk"]
    assert c.source_bonus("hackernews", pri) == 0.15
    assert c.source_bonus("arstechnica", pri) == 0.10
    assert c.source_bonus("nrk", pri) == 0.05
    assert c.source_bonus("bbc", pri) == 0.0          # unlisted: no bonus


def test_source_bonus_fuzzy_match():
    # display "BBC News" -> token "bbcnews"; slug "bbc" should still match
    assert c.source_bonus("bbc", ["bbcnews"]) == 0.15


def test_recency_bonus():
    assert c.recency_bonus(TODAY, TODAY) == 0.1
    assert c.recency_bonus(TODAY - dt.timedelta(days=1), TODAY) == 0.05
    assert c.recency_bonus(TODAY - dt.timedelta(days=5), TODAY) == 0.0
    assert c.recency_bonus(None, TODAY) == 0.0


# --------------------------------------------------------------- scoring
def test_score_weighted_sum_plus_bonuses():
    prefs = c.Prefs(interests={"Tech": 0.9}, source_priority=["hackernews"],
                    reading_minutes=20, max_articles=14, reading_profile="", feedback=[])
    a = make("x", "hackernews", "Tech", match={"Tech": 1.0})
    # 1.0*0.9 + 0.15 (source) + 0.1 (today) = 1.15
    assert c.score(a, prefs, TODAY) == pytest.approx(1.15)


def test_feedback_hide_excludes():
    prefs = c.Prefs(interests={"Crypto": 0.7}, source_priority=[], reading_minutes=20,
                    max_articles=14, reading_profile="",
                    feedback=[{"date": "2026-06-01", "signal": "hide", "text": "no crypto"}])
    a = make("x", "src", "Crypto", match={"Crypto": 0.9})
    assert c.score(a, prefs, TODAY) == -1.0


def test_feedback_more_boosts():
    base_prefs = c.Prefs(interests={"AI": 0.5}, source_priority=[], reading_minutes=20,
                         max_articles=14, reading_profile="", feedback=[])
    boosted = c.Prefs(interests={"AI": 0.5}, source_priority=[], reading_minutes=20,
                      max_articles=14, reading_profile="",
                      feedback=[{"date": "2026-06-01", "signal": "more", "text": "more AI"}])
    a1 = make("x", "s", "AI", match={"AI": 1.0})
    a2 = make("x", "s", "AI", match={"AI": 1.0})
    assert c.score(a2, boosted, TODAY) > c.score(a1, base_prefs, TODAY)


# --------------------------------------------------------------- selection
def test_diversify_topic_cap():
    arts = [make(f"t{i}", "s", "Tech", date=TODAY) for i in range(10)]
    for i, a in enumerate(arts):
        a.score = 1.0 - i * 0.01
    kept = c.diversify(arts, max_articles=14)
    assert len(kept) == 5                              # ceil(0.3*14) = 5 per topic


def test_diversify_drops_negative_scores():
    a = make("hidden", "s", "Tech")
    a.score = -1.0
    assert c.diversify([a], 14) == []


def test_balance_source_cap():
    arts = [make(f"n{i}", "nrk", "Norge") for i in range(10)]
    arts += [make(f"h{i}", "hackernews", "Tech") for i in range(3)]
    for i, a in enumerate(arts):
        a.score = 1.0 - i * 0.01
    chosen = c.balance_sources(arts, max_articles=14, priority=["hackernews"])
    nrk = [a for a in chosen if a.source == "nrk"]
    assert len(nrk) <= 5                               # floor(0.4*14) = 5 per source


def test_assign_roles_distribution():
    arts = [make(f"a{i}", "s", "Tech") for i in range(11)]
    for i, a in enumerate(arts):
        a.score = 1.0 - i * 0.01
    ranked = c.assign_roles(arts, reading_minutes=20)
    roles = [a.role for a in ranked]
    assert roles[0] == "lead"
    assert roles.count("lead") == 1
    assert roles.count("lg") == 3                      # 20 min -> 3 lg, 4 md
    assert roles.count("md") == 4
    assert roles.count("brief") == 3


def test_assign_roles_short_read_more_briefs():
    arts = [make(f"a{i}", "s", "Tech") for i in range(11)]
    for i, a in enumerate(arts):
        a.score = 1.0 - i * 0.01
    ranked = c.assign_roles(arts, reading_minutes=10)
    roles = [a.role for a in ranked]
    assert roles.count("lg") == 2                      # <15 min -> fewer majors
    assert roles.count("brief") > 3


def test_bad_title_rejects_masthead_echo():
    # The model sometimes echoes the "OpenPaper" masthead from the reading profile.
    assert c._bad_title("OpenPaper")
    assert c._bad_title('  "openpaper" ')
    assert c._bad_title("")
    assert c._bad_title(None)
    # A real headline is fine.
    assert not c._bad_title("Havvind-drama på Stortinget")
