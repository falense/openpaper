# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pyyaml"]
# ///
"""OpenPaper local curation engine — agent-free, runs on a local model.

This is the `engine: local` alternative to Claude-driven curation. The split is
deliberate and is what lets a small local model produce a good paper:

  * ALL editorial arithmetic — interest weights, source/recency bonuses, the
    topic/source/serendipity caps, role assignment — is deterministic Python
    in `curation_core.py`, matching `references/curation-guide.md`. It is
    unit-tested, reproducible, and shared with the Claude `ranking: deterministic`
    flow (`rank.py`) so the two engines cannot drift apart.
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
import subprocess
import sys
from pathlib import Path

import httpx
import yaml

# Deterministic core — re-exported so existing imports (and tests) keep working.
from curation_core import (  # noqa: F401
    DEFAULT_CONFIG, LEVEL_WEIGHTS, SOURCE_BONUS, FEEDBACK_SIGNALS,
    Article, Prefs, load_config, load_incoming, parse_preferences,
    source_bonus, recency_bonus, feedback_multiplier, score,
    diversify, balance_sources, assign_roles, select_plan, _norm,
)

HERE = Path(__file__).resolve().parent
FETCHERS = HERE.parent / "fetchers"

# role -> (max paragraphs enforced in code, prompt spec)
ROLE_SPEC = {
    "lead": (4, 'Skriv 3-4 avsnitt med narrativ bue. JSON: {"title","kicker","deck","paragraphs":[..],"photo_caption","annotation"}.'),
    "lg": (2, 'Skriv nøyaktig 2 avsnitt. JSON: {"title","kicker","paragraphs":[..]}.'),
    "md": (1, 'Skriv ett stramt avsnitt. JSON: {"title","kicker","paragraphs":["..."]}.'),
    "brief": (0, 'Skriv én setning, maks 15 ord. JSON: {"bold":"tema","text":"setning."}.'),
}


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

    plan = select_plan(arts, prefs, today)
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
