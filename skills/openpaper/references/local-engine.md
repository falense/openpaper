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
| Interest weights, source/recency bonuses, feedback decay | **Code** (`curation_core.py`) |
| Topic cap (30%), source cap (40%), serendipity (20%) | **Code** |
| Role assignment (lead / lg / md / brief), role-length limits | **Code** |
| Per-article semantic match against the reader's interests | **Model** |
| Role-calibrated article summaries | **Model** |
| Weather, markets, rendering | existing scripts (unchanged) |

All the arithmetic lives in `curation_core.py`, mirrors
[`curation-guide.md`](curation-guide.md), and is unit-tested
(`tests/test_curate.py`). The model only ever answers narrow, per-article
questions — which is what keeps a 2–4B model reliable.

### The same arithmetic, from the Claude engine

`curation_core` is engine-agnostic, so the Claude engine can reuse it too. With
`engine: claude` + `ranking: deterministic` (see
[`config.example.yaml`](config.example.yaml)), the `/openpaper` skill scores
relevance itself — Claude-quality judgement on full article text — then runs the
selection through `rank.py`, which calls the very same
`score → diversify → balance_sources → assign_roles` pipeline. The two engines
then differ only in *who scores relevance and writes the summaries*, not in the
editorial caps or role tiers. The local model's only structural disadvantage is
the relevance judgement (the table's one `Model` row for matching); swapping in
Claude there, while keeping the deterministic selection, is what
`ranking: deterministic` buys.

## Enable it

1. Install [Ollama](https://ollama.com) and pull a model:

   ```bash
   ollama serve &
   ollama pull gemma4:e4b-it-q4_K_M
   ```

2. Set the engine in `.openpaper/config.yaml` (see
   [`config.example.yaml`](config.example.yaml)):

   ```yaml
   engine: local
   model: gemma4:e4b-it-q4_K_M
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

**Use an instruction-tuned (`-it`) model.** The base Gemma checkpoints
(`gemma4:e4b`, `gemma4:e2b`, no `-it` suffix) ship with a raw completion
template and do not follow the JSON-output and summarisation instructions — they
tend to translate or continue the article verbatim instead. The `-it` variants
are what make the per-article matching and role-calibrated summaries reliable.
Ollama publishes `-it` only as fully-qualified tags (`…-q4_K_M`, `…-qat`,
`…-q8_0`, `…-bf16`) — there is no bare `:e4b-it` alias.

- **`gemma4:e4b-it-q4_K_M` — recommended default.** Instruction-tuned 8B at
  q4_K_M (same quant as, and byte-identical to, the old `gemma4:e4b` tag).
  Faithful summaries, fluent bokmål, ~4 min for a 14-article edition on an
  M-series Mac. Fastest *and* most reliable option in the benchmark.
- **12B — not recommended (benchmarked worse, both quants).** In
  `.openpaper/bench/REPORT.md`, `gemma4:12b-it-q4_K_M` was ~1.8× slower (~7.5 min)
  *and* unreliable (empty story bodies incl. the lead, title corruption,
  untranslated text). `gemma4:12b-it-q8_0` was far worse: memory-bound on a 48 GB
  Mac at 32k context (~2.4 tok/s, heavy swap), ~12× slower, and a runaway
  generation forced an abort. Bigger is not better here — e4b-it wins on speed
  and reliability. (`gemma4:12b-it-qat` at a smaller context is the only 12B
  option left untested.)
- **Base (non-`-it`) and `gemma4:e2b` — not recommended.** Base models ignore
  the instructions; e2b is too weak to summarise.
- Any other Ollama model works via `model:`; larger `-it` models reduce the
  language slips below.

Benchmark the options yourself against your own corpus:

```bash
uv run skills/openpaper/scripts/bench.py --data-dir .openpaper \
  --models gemma4:e4b-it-q4_K_M gemma4:12b-it-q4_K_M
```

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
- `scripts/bench.py` — times the curation pipeline across models (per-phase
  wall-clock), writes editions to `.openpaper/bench/` for quality comparison.
- `tests/test_curate.py` — unit tests for the deterministic parts.
