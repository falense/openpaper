# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pyyaml"]
# ///
"""Benchmark the local curation engine across models — per-phase wall-clock.

Runs the REAL `curate.py` code path (per-article semantic matching + the
role-calibrated summaries) against the current `incoming/` corpus, once per
model, and reports how long each phase takes. Each model's edition YAML is
written to `.openpaper/bench/` so the output quality can be compared
side-by-side.

    uv run skills/openpaper/scripts/bench.py --data-dir .openpaper \
        --models gemma4:e4b-it gemma4:12b-it

It is non-destructive: it never fetches and never archives. It only reads
`incoming/` and writes under `bench/`, so the same corpus stays intact for
comparing engines — including the Claude agent flow, whose wall-clock is
measured separately and pasted into the report by hand.

Notes on fairness:
  * Each model gets a warm-up generation before timing, so the one-time
    model-load cost is not charged to the matching phase.
  * Matching runs at temperature 0 (num_ctx 8192); summaries at temperature 0.5
    (num_ctx 32768) — identical to curate.py. The summary phase includes
    curate.py's one retry on malformed output, so it reflects real cost.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import curate as C  # reuse the real pipeline — we measure exactly what runs in prod


def _fresh_inputs(data_dir: Path):
    """Reload prefs + a fresh set of Article objects (curate mutates them)."""
    prefs = C.parse_preferences((data_dir / "preferences.md").read_text())
    arts = C.load_incoming(data_dir)
    return prefs, arts


def bench_model(model: str, data_dir: Path, base_cfg: dict, today: dt.date) -> dict:
    cfg = {**base_cfg, "model": model}
    C.ensure_ollama(cfg)
    prefs, arts = _fresh_inputs(data_dir)
    interests = list(prefs.interests)

    # Warm-up: load the model into memory so its cold-load cost isn't charged
    # to the first matching call.
    print(f"\n[{model}] warming up…", file=sys.stderr)
    C._generate(cfg, "", "hei", temperature=0.0, num_ctx=512)

    # Phase 1 — semantic matching (one model call per article).
    print(f"[{model}] matching {len(arts)} articles…", file=sys.stderr)
    t0 = time.perf_counter()
    for a in arts:
        a.match = C.semantic_match(a, interests, cfg)
        a.score = C.score(a, prefs, today)
    match_s = time.perf_counter() - t0

    # Deterministic selection + role assignment (no model — not timed as a phase).
    plan = C.assign_roles(
        C.balance_sources(
            C.diversify(arts, prefs.max_articles), prefs.max_articles, prefs.source_priority
        ),
        prefs.reading_minutes,
    )
    roles = {}
    for a in plan:
        roles[a.role] = roles.get(a.role, 0) + 1

    # Phase 2 — role-calibrated summaries (one or two model calls per article).
    print(f"[{model}] summarising {len(plan)} selected articles…", file=sys.stderr)
    t1 = time.perf_counter()
    for a in plan:
        a.summary_json = C.summarise(a, prefs.reading_profile, cfg)
    summary_s = time.perf_counter() - t1

    # Word of the day — one more small model call (part of every edition).
    t2 = time.perf_counter()
    wod = C.word_of_day(prefs.reading_profile, cfg)
    wod_s = time.perf_counter() - t2

    edition = C.assemble_edition(plan, prefs, cfg, today)
    edition["word_of_day"] = wod  # assemble_edition already calls it; keep the timed one

    out = data_dir / "bench" / f"edition-{model.replace(':', '_').replace('/', '_')}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(edition, allow_unicode=True, sort_keys=False))

    model_total = match_s + summary_s + wod_s
    return {
        "model": model,
        "n_matched": len(arts),
        "match_s": match_s,
        "match_per_article": match_s / max(1, len(arts)),
        "n_selected": len(plan),
        "roles": roles,
        "summary_s": summary_s,
        "summary_per_article": summary_s / max(1, len(plan)),
        "wod_s": wod_s,
        "model_total_s": model_total,
        "edition_path": str(out),
        "lead_title": (edition.get("lead") or {}).get("title", ""),
    }


def _fmt(s: float) -> str:
    return f"{s:5.1f}s" if s < 60 else f"{s / 60:4.1f}m"


def render_report(results: list[dict], today: dt.date) -> str:
    lines = [
        "# OpenPaper curation benchmark",
        "",
        f"Corpus: `{results[0]['n_matched']}` incoming articles · generated {today.isoformat()}.",
        "Local models run single-stream through Ollama (the real per-edition cost).",
        "",
        "## Timing (model work only)",
        "",
        "| Model | Match (total / per art.) | Summarise (total / per art.) | Word/day | **Model total** |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| `{r['model']}` "
            f"| {_fmt(r['match_s'])} / {r['match_per_article']:.1f}s "
            f"| {_fmt(r['summary_s'])} ({r['n_selected']} art.) / {r['summary_per_article']:.1f}s "
            f"| {_fmt(r['wod_s'])} "
            f"| **{_fmt(r['model_total_s'])}** |"
        )
    lines += [
        "",
        "> The Claude (default) engine runs the same selection as an editorial",
        "> judgment and summarises with parallel subagents, so its wall-clock is",
        "> measured from the real agent flow and added below by hand — it is not",
        "> single-stream and not directly comparable to the local rows.",
        "",
        "## Selection / output (quick quality glance)",
        "",
    ]
    for r in results:
        lines.append(f"- **`{r['model']}`** → roles {r['roles']}; lead: “{r['lead_title']}”")
        lines.append(f"  - edition: `{r['edition_path']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark the local curation engine across models")
    ap.add_argument("--data-dir", type=Path, default=Path(".openpaper"))
    ap.add_argument("--models", nargs="+", required=True, help="Ollama model tags to benchmark")
    args = ap.parse_args()

    data_dir = args.data_dir.resolve()
    base_cfg = C.load_config(data_dir)
    today = dt.date.today()

    if not (data_dir / "incoming").glob("*.json"):
        sys.exit("Error: no articles in incoming/. Run fetch_all.py first.")

    results = []
    for model in args.models:
        results.append(bench_model(model, data_dir, base_cfg, today))

    report = render_report(results, today)
    report_path = data_dir / "bench" / "REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)

    print("\n" + report, file=sys.stderr)
    print(str(report_path))


if __name__ == "__main__":
    main()
