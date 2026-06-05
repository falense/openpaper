# Local curation engine

OpenPaper's default engine is Claude: the `/openpaper` skill acts as
editor-in-chief, scoring, selecting, and summarising articles. The **local
engine** is an opt-in alternative that runs the same pipeline with a small local
model and **no Claude Code session** — private, offline, and free to run, at the
cost of some editorial polish.

This document describes how it works, how to enable it, and its limits.

## Design: code does the judgment, the model does the prose

A small local model is a poor editor — asked for a single holistic relevance
score it skews toward surface topicality and undervalues major human-interest
stories. So the local engine splits the work along the line of what each side is
actually good at:

| Work | Done by |
| --- | --- |
| Interest weights, source/recency bonuses, feedback decay | **Code** (`curate.py`) |
| Topic cap (30%), source cap (40%), serendipity (20%) | **Code** |
| Role assignment (lead / lg / md / brief), role-length limits | **Code** |
| Per-article semantic match against the reader's interests | **Model** |
| Role-calibrated article summaries | **Model** |
| Weather, markets, rendering | existing scripts (unchanged) |

All the arithmetic mirrors [`curation-guide.md`](curation-guide.md) and is
unit-tested (`tests/test_curate.py`). The model only ever answers narrow,
per-article questions — which is what keeps a 2–4B model reliable.

## Enable it

1. Install [Ollama](https://ollama.com) and pull a model:

   ```bash
   ollama serve &
   ollama pull gemma4:e4b
   ```

2. Set the engine in `.openpaper/config.yaml` (see
   [`config.example.yaml`](config.example.yaml)):

   ```yaml
   engine: local
   model: gemma4:e4b
   ```

3. Make a paper without Claude:

   ```bash
   uv run skills/openpaper/scripts/make_paper.py --data-dir .openpaper
   ```

   `make_paper.py` chains `fetch_all.py` → `curate.py` → `render.py`, then
   launches the preview server (`serve.py`) and opens the edition in your
   browser — the same UX as the Claude flow. It serves until you press Ctrl+C.
   Use `--skip-fetch` to re-curate the current `incoming/` without re-fetching,
   and `--no-serve` for headless/cron runs that should just render and exit.

You can also run curation alone:

```bash
uv run skills/openpaper/scripts/curate.py --data-dir .openpaper --output .openpaper/editions/draft.yaml
```

## Model choice

- **`gemma4:e4b` — recommended.** Faithful summaries, fluent prose, ~12 s per
  article (a 14-article edition ≈ 3 min on an M-series Mac).
- **`gemma4:e2b` — not recommended.** Too weak: it tends to translate whole
  articles verbatim instead of summarising.
- Any other Ollama model works via `model:`; larger local models reduce the
  language slips below.

## Known limits (vs. the Claude engine)

- **Editorial judgment is weaker.** Selection leans more on raw topic match;
  the deterministic rules compensate but won't match Claude's taste for the
  single most *interesting* lead.
- **Occasional language slips** on terse outputs (e.g. wrong Scandinavian
  variant, a literal title). Guards retry once and enforce role length, but a
  per-locale post-check is a future improvement.
- **Out of scope for now:** embeddings-based matching (would remove the
  generative model from selection entirely), a feedback-writing loop, and
  runtimes other than Ollama (llama.cpp/MLX).

## Files

- `scripts/curate.py` — config + preference parsing, deterministic scoring,
  model layer, edition assembly.
- `scripts/make_paper.py` — agent-free fetch → curate → render orchestrator.
- `tests/test_curate.py` — unit tests for the deterministic parts.
