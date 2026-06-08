# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""OpenPaper deterministic curation core — engine-agnostic, no language model.

This module holds ALL the editorial arithmetic from `references/curation-guide.md`:
preference parsing, interest scoring, the topic/source/serendipity caps and role
assignment. It is pure (stdlib + pyyaml), unit-tested and reproducible.

It is deliberately the *only* place this logic lives, so both curation engines
share it instead of drifting apart:

  * `curate.py`  — the `engine: local` flow: this core + a local model (Ollama)
    for semantic matching and summaries.
  * `rank.py`    — the `engine: claude` + `ranking: deterministic` flow: this core
    fed with Claude-supplied match scores, so the agent gets the same
    reproducible selection and role tiers as the local engine, then writes the
    summaries itself.

The one input this core does NOT compute is the per-article semantic match against
the reader's interests (`Article.match`) — that genuinely needs a language model,
and which model supplies it is exactly what differs between the two engines.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "engine": "claude",
    "ranking": "agent",                # engine: claude only — "agent" | "deterministic"
    "model": "gemma4:e4b-it-q4_K_M",   # instruction-tuned; the base gemma4:e4b ignores the JSON/summary instructions
    "ollama_url": "http://localhost:11434",
    "location": "Oslo, Norway",
    "tagline": "All the news that fits the day you are about to have.",
    "ui": None,            # optional dict of localised template labels
}

# Natural-language interest level -> weight (curation-guide.md §1).
LEVEL_WEIGHTS = [
    (("very interested", "essential", "always"), 0.9),
    (("interested", "like", "enjoy"), 0.7),
    (("some interest", "occasionally"), 0.5),
    (("passing interest", "sometimes"), 0.3),
]
SOURCE_BONUS = [0.15, 0.10, 0.05]          # positions 1-3; 4+ -> 0.02
FEEDBACK_SIGNALS = {"love": 1.5, "more": 1.2, "less": 0.5, "hide": -999.0}


# --------------------------------------------------------------------------- #
# Config + preferences (the source of truth — no duplicated interest lists)
# --------------------------------------------------------------------------- #
def load_config(data_dir: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = data_dir / "config.yaml"
    if path.exists():
        loaded = yaml.safe_load(path.read_text()) or {}
        if isinstance(loaded.get("local"), dict):     # allow a nested local: block
            loaded = {**loaded, **loaded.pop("local")}
        cfg.update({k: v for k, v in loaded.items() if v is not None or k == "ui"})
    return cfg


@dataclass
class Prefs:
    interests: dict[str, float]
    source_priority: list[str]                 # normalised tokens, in order
    reading_minutes: int
    max_articles: int
    reading_profile: str                       # freeform text -> model style/language
    feedback: list[dict]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _weight_for(level: str) -> float:
    low = level.lower()
    for keys, w in LEVEL_WEIGHTS:
        if any(k in low for k in keys):
            return w
    return 0.5


def _sections(text: str) -> dict[str, str]:
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.*)", line)
        if m:
            if name is not None:
                out[name.lower()] = "\n".join(buf)
            name, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    if name is not None:
        out[name.lower()] = "\n".join(buf)
    return out


def parse_preferences(text: str) -> Prefs:
    sec = _sections(text)

    interests: dict[str, float] = {}
    for line in sec.get("interests", "").splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)", line)
        if not m:
            continue
        item = m.group(1)
        name = re.split(r"\s[—–-]\s|\(", item, maxsplit=1)[0].strip()  # before "(" or spaced dash
        lvl = re.search(r"\(([^)]*)\)", item)
        if name:
            interests[name] = _weight_for(lvl.group(1) if lvl else "")

    source_priority: list[str] = []
    for line in sec.get("sources", "").splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)", line)
        if not m:
            continue
        disp = re.split(r"[—(]", m.group(1), maxsplit=1)[0]
        disp = re.split(r"\s[-–]\s", disp, maxsplit=1)[0].strip()
        if disp:
            source_priority.append(_norm(disp))

    profile = sec.get("reading profile", "")
    am = re.search(r"(\d+)\s*articles", profile, re.I)
    mm = re.search(r"(\d+)\s*min", profile, re.I)

    feedback: list[dict] = []
    for line in sec.get("feedback", "").splitlines():
        m = re.match(r"^\s*[-*]\s+(\d{4}-\d{2}-\d{2})\s*[:\-]\s*(.+)", line)
        if not m:
            continue
        rest = m.group(2)
        sig = next((s for s in FEEDBACK_SIGNALS if s in rest.lower()), None)
        if sig:
            feedback.append({"date": m.group(1), "signal": sig, "text": rest})

    return Prefs(
        interests=interests or {"general news": 0.5},
        source_priority=source_priority,
        reading_minutes=int(mm.group(1)) if mm else 20,
        max_articles=int(am.group(1)) if am else 14,
        reading_profile=profile.strip(),
        feedback=feedback,
    )


# --------------------------------------------------------------------------- #
# Articles
# --------------------------------------------------------------------------- #
@dataclass
class Article:
    title: str
    source: str
    date: dt.date | None
    summary: str
    content: str
    url: str
    image_url: str | None
    file: str
    match: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    primary_topic: str = ""
    role: str = ""
    summary_json: dict = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.file[:-5] if self.file.endswith(".json") else self.file


def load_incoming(data_dir: Path) -> list[Article]:
    arts = []
    for p in sorted((data_dir / "incoming").glob("*.json")):
        d = json.loads(p.read_text())
        try:
            date = dt.datetime.fromisoformat(d["date"]).date() if d.get("date") else None
        except Exception:
            date = None
        arts.append(Article(
            title=d.get("title", "Untitled"), source=d.get("source", ""), date=date,
            summary=d.get("summary", ""), content=d.get("content") or "",
            url=d.get("url", ""), image_url=d.get("image_url"), file=p.name,
        ))
    return arts


# --------------------------------------------------------------------------- #
# Deterministic scoring (curation-guide.md §1-§4) — pure, unit-tested
# --------------------------------------------------------------------------- #
def source_bonus(source: str, priority: list[str]) -> float:
    s = _norm(source)
    for i, tok in enumerate(priority):
        if tok and (tok in s or s in tok):
            return SOURCE_BONUS[i] if i < len(SOURCE_BONUS) else 0.02
    return 0.0


def recency_bonus(date: dt.date | None, today: dt.date) -> float:
    if date is None:
        return 0.0
    days = (today - date).days
    return 0.1 if days <= 0 else 0.05 if days == 1 else 0.0


def feedback_multiplier(art: Article, prefs: Prefs, today: dt.date) -> float:
    mult = 1.0
    for fb in prefs.feedback:
        topics = [name for name in prefs.interests
                  if art.match.get(name, 0.0) >= 0.3 and name.lower() in fb["text"].lower()]
        if not topics:
            continue
        try:
            age = (today - dt.date.fromisoformat(fb["date"])).days
        except Exception:
            age = 0
        decay = 1.0 if age <= 30 else 0.5 if age <= 90 else 0.25
        signal = FEEDBACK_SIGNALS[fb["signal"]]
        if signal < 0:
            return -1000.0                      # hide -> exclude
        mult *= 1 + (signal - 1) * decay
    return mult


def score(art: Article, prefs: Prefs, today: dt.date) -> float:
    base = sum(art.match.get(name, 0.0) * w for name, w in prefs.interests.items())
    s = (base + source_bonus(art.source, prefs.source_priority)
         + recency_bonus(art.date, today)) * feedback_multiplier(art, prefs, today)
    art.primary_topic = max(art.match, key=art.match.get) if art.match else ""
    return -1.0 if s < -100 else round(s, 3)


def diversify(arts: list[Article], max_articles: int) -> list[Article]:
    cap = math.ceil(0.3 * max_articles)
    kept, per_topic = [], {}
    for a in sorted(arts, key=lambda x: x.score, reverse=True):
        if a.score < 0:
            continue
        n = per_topic.get(a.primary_topic, 0)
        if n < cap:
            kept.append(a)
            per_topic[a.primary_topic] = n + 1
    return kept


def balance_sources(arts: list[Article], max_articles: int, priority: list[str]) -> list[Article]:
    src_cap = max(1, math.floor(0.4 * max_articles))
    serendipity_min = math.ceil(0.2 * max_articles)
    top3 = set(priority[:3])
    pool = sorted(arts, key=lambda x: x.score, reverse=True)
    chosen, per_src = [], {}
    for a in pool:
        if len(chosen) >= max_articles:
            break
        if per_src.get(a.source, 0) < src_cap:
            chosen.append(a)
            per_src[a.source] = per_src.get(a.source, 0) + 1
    outsiders = [a for a in chosen if not any(t in _norm(a.source) for t in top3)]
    if len(outsiders) < serendipity_min:
        for a in pool:
            if a in chosen:
                continue
            if not any(t in _norm(a.source) for t in top3):
                chosen.append(a)
                if len([x for x in chosen if not any(t in _norm(x.source) for t in top3)]) >= serendipity_min:
                    break
    return chosen[:max_articles]


def assign_roles(arts: list[Article], reading_minutes: int) -> list[Article]:
    n_lg, n_md = (2, 3) if reading_minutes < 15 else (3, 4)
    ranked = sorted(arts, key=lambda x: x.score, reverse=True)
    for i, a in enumerate(ranked):
        a.role = ("lead" if i == 0 else "lg" if i <= n_lg
                  else "md" if i <= n_lg + n_md else "brief")
    return ranked


def select_plan(arts: list[Article], prefs: Prefs, today: dt.date) -> list[Article]:
    """Full deterministic pipeline: score-ordered, diversified, source-balanced,
    role-assigned. Expects each article's `.match` and `.score` to be set already
    (call `score()` per article first). Returns the ordered edition plan."""
    return assign_roles(
        balance_sources(diversify(arts, prefs.max_articles), prefs.max_articles, prefs.source_priority),
        prefs.reading_minutes,
    )
