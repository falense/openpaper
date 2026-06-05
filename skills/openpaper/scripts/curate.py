# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pyyaml"]
# ///
"""OpenPaper local curation engine — agent-free, runs on a local model.

This is the `engine: local` alternative to Claude-driven curation. The split is
deliberate and is what lets a small local model produce a good paper:

  * ALL editorial arithmetic — interest weights, source/recency bonuses, the
    topic/source/serendipity caps, role assignment — is deterministic Python
    here, matching `references/curation-guide.md`. It is unit-tested and
    reproducible.
  * The local model (via Ollama) does only the two things that genuinely need a
    language model: per-article semantic matching against the reader's interests,
    and the role-calibrated summaries.

Reads `.openpaper/incoming/*.json` + `preferences.md` + `config.yaml`, writes an
edition YAML that `render.py` consumes. See `references/local-engine.md`.

Usage:
    uv run curate.py --data-dir .openpaper --output .openpaper/editions/draft.yaml
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
FETCHERS = HERE.parent / "fetchers"

DEFAULT_CONFIG = {
    "engine": "claude",
    "model": "gemma4:e4b",
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

# role -> (max paragraphs enforced in code, prompt spec)
ROLE_SPEC = {
    "lead": (4, 'Skriv 3-4 avsnitt med narrativ bue. JSON: {"title","kicker","deck","paragraphs":[..],"photo_caption","annotation"}.'),
    "lg": (2, 'Skriv nøyaktig 2 avsnitt. JSON: {"title","kicker","paragraphs":[..]}.'),
    "md": (1, 'Skriv ett stramt avsnitt. JSON: {"title","kicker","paragraphs":["..."]}.'),
    "brief": (0, 'Skriv én setning, maks 15 ord. JSON: {"bold":"tema","text":"setning."}.'),
}


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


# --------------------------------------------------------------------------- #
# Local model layer (Ollama) — the only part that needs a language model
# --------------------------------------------------------------------------- #
def ensure_ollama(cfg: dict) -> None:
    try:
        httpx.get(cfg["ollama_url"] + "/api/version", timeout=5.0).raise_for_status()
    except Exception:
        sys.exit(
            f"Error: cannot reach Ollama at {cfg['ollama_url']}.\n"
            f"Start it with `ollama serve` and pull the model: "
            f"`ollama pull {cfg['model']}`."
        )


def _generate(cfg: dict, system: str, prompt: str, *, temperature: float, num_ctx: int = 32768) -> dict:
    r = httpx.post(cfg["ollama_url"] + "/api/generate", json={
        "model": cfg["model"], "system": system, "prompt": prompt, "stream": False,
        "format": "json", "options": {"num_ctx": num_ctx, "temperature": temperature},
    }, timeout=300.0)
    r.raise_for_status()
    try:
        return json.loads(r.json()["response"])
    except Exception:
        return {}


def semantic_match(art: Article, interests: list[str], cfg: dict) -> dict[str, float]:
    system = (
        "Vurder hvor sterkt artikkelen handler om hvert tema, 0.0-1.0. "
        'Returner KUN JSON: {"' + '": <0-1>, "'.join(interests) + '": <0-1>}.'
    )
    prompt = f"TITTEL: {art.title}\nSAMMENDRAG: {art.summary}\nUTDRAG: {art.content[:600]}"
    raw = _generate(cfg, system, prompt, temperature=0.0, num_ctx=8192)
    return {k: max(0.0, min(1.0, float(raw.get(k, 0.0) or 0.0))) for k in interests}


def _bad_title(t: str) -> bool:
    """True if a model-generated headline is empty or just echoes the masthead.

    The reading profile is injected into the summary prompt and mentions the
    "OpenPaper" masthead; small models sometimes copy it into the title field.
    """
    t = (t or "").strip().strip('"').strip()
    return not t or t.lower() == "openpaper"


def summarise(art: Article, style: str, cfg: dict) -> dict:
    cap, spec = ROLE_SPEC[art.role]
    system = (f"Du skriver en avissak i rollen «{art.role}». {spec}\n"
              f"FØLG leserprofilen for språk og stil:\n{style}\n"
              "Svar KUN med gyldig JSON.")
    prompt = f"TITTEL: {art.title}\nKILDE: {art.source}\n\nARTIKKEL:\n{art.content[:12000]}"
    j = _generate(cfg, system, prompt, temperature=0.5)
    need_title = art.role != "brief"
    missing = (not j.get("paragraphs") if art.role != "brief" else not j.get("text"))
    if missing or (need_title and _bad_title(j.get("title"))):
        j = _generate(cfg, system + "\nVIKTIG: ta med ALLE JSON-felt, vær tro mot kilden.",
                      prompt, temperature=0.2)
    if art.role != "brief":
        j["paragraphs"] = [p for p in j.get("paragraphs", []) if p][:cap]
    if need_title and _bad_title(j.get("title")):
        j["title"] = art.title          # fall back to the real source headline
    return j


def word_of_day(style: str, cfg: dict) -> dict:
    try:
        j = _generate(cfg, "Velg et interessant «dagens ord». FØLG språket i leserprofilen:\n"
                      + style + '\nReturner KUN JSON {"word","definition"}.', "Dagens ord.",
                      temperature=0.8, num_ctx=2048)
        if j.get("word") and j.get("definition"):
            return {"word": j["word"], "definition": j["definition"]}
    except Exception:
        pass
    return {"word": "Serendipitet", "definition": "et lykkelig sammentreff i oppdagelse"}


# --------------------------------------------------------------------------- #
# Edition assembly
# --------------------------------------------------------------------------- #
def _run_fetcher(path: Path, args: list[str], fallback):
    try:
        out = subprocess.run(["uv", "run", str(path), *args],
                             capture_output=True, text=True, timeout=120, cwd=HERE.parents[2])
        return json.loads(out.stdout) if out.stdout.strip() else fallback
    except Exception:
        return fallback


def assemble_edition(plan: list[Article], prefs: Prefs, cfg: dict, today: dt.date) -> dict:
    lead_art = plan[0]
    lj = lead_art.summary_json
    lead = {
        "kicker": "The Lead · " + (lj.get("kicker") or lead_art.primary_topic.title()),
        "title": (lj.get("title") or lead_art.title),
        "deck": lj.get("deck", ""),
        "byline": "By the OpenPaper Desk",
        "url": lead_art.url, "image_url": lead_art.image_url,
        "paragraphs": lj.get("paragraphs", []),
        "annotation": lj.get("annotation", f"because you follow {lead_art.primary_topic}"),
        "photo_caption": lj.get("photo_caption", ""),
    }

    cols = ["col2", "col3", "col4", "col1", "col5", "col2", "col3", "col4"]
    stories, briefs, seen, ci = [], [], set(), 0
    for a in plan[1:]:
        j = a.summary_json
        if a.role == "brief":
            text = j.get("text", "")
            key = " ".join(text.lower().split()[:4])
            if not text or key in seen:
                continue
            seen.add(key)
            briefs.append({"bold": j.get("bold") or a.primary_topic.title(),
                           "text": text, "url": a.url})
        else:
            story = {"kicker": (j.get("kicker") or a.primary_topic.title())[:48],
                     "title": (j.get("title") or a.title), "size": a.role,
                     "section": cols[ci % len(cols)], "url": a.url,
                     "paragraphs": j.get("paragraphs", [])}
            if a.role == "lg" and a.image_url:
                story["image_url"], story["has_thumb"] = a.image_url, True
            stories.append(story)
            ci += 1

    topics, sections = [], []
    pages = ["A1", "A3", "A5", "A7", "B1"]
    for a in plan:
        if a.primary_topic and a.primary_topic not in topics:
            topics.append(a.primary_topic)
    for i, t in enumerate(topics[:5]):
        sections.append({"name": t.title(), "page": pages[i]})

    date_str = today.strftime("%A, %B ") + str(today.day) + today.strftime(", %Y")
    edition = {
        "template": "broadsheet", "edition_name": "morning",
        "date": date_str, "date_formal": date_str,
        "volume": "auto", "number": "auto",
        "location": cfg["location"], "reading_time": f"{prefs.reading_minutes} min",
        "article_count": 1 + len(stories) + len(briefs),
        "tagline": cfg["tagline"],
        "printed_time": dt.datetime.now().strftime("%H:%M"),
        "weather": _run_fetcher(FETCHERS / "weather.py", [],
                                {"icon": "cloud", "temp": 0, "description": "",
                                 "high": 0, "low": 0, "wind": "", "forecast": []}),
        "markets": _run_fetcher(FETCHERS / "markets.py", [], []),
        "lead": lead, "stories": stories, "briefs": briefs,
        "sections_index": sections,
        "word_of_day": word_of_day(prefs.reading_profile, cfg),
    }
    if cfg.get("ui"):
        edition["ui"] = cfg["ui"]
    return edition


# --------------------------------------------------------------------------- #
def curate(data_dir: Path, cfg: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    prefs = parse_preferences((data_dir / "preferences.md").read_text())
    arts = load_incoming(data_dir)
    if not arts:
        sys.exit("Error: no articles in incoming/. Run fetch_all.py first.")

    ensure_ollama(cfg)
    interests = list(prefs.interests)
    print(f">> Matching {len(arts)} articles against {len(interests)} interests…", file=sys.stderr)
    for a in arts:
        a.match = semantic_match(a, interests, cfg)
        a.score = score(a, prefs, today)

    plan = assign_roles(
        balance_sources(diversify(arts, prefs.max_articles), prefs.max_articles, prefs.source_priority),
        prefs.reading_minutes)
    print(f">> Selected {len(plan)} articles; summarising…", file=sys.stderr)
    for a in plan:
        a.summary_json = summarise(a, prefs.reading_profile, cfg)

    return assemble_edition(plan, prefs, cfg, today)


def main() -> None:
    ap = argparse.ArgumentParser(description="OpenPaper local curation engine")
    ap.add_argument("--data-dir", type=Path, default=Path(".openpaper"))
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()

    cfg = load_config(args.data_dir)
    edition = curate(args.data_dir.resolve(), cfg)

    out = args.output or (args.data_dir / "editions" / "draft.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(edition, allow_unicode=True, sort_keys=False))
    print(str(out))


if __name__ == "__main__":
    main()
