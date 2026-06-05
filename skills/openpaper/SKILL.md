---
name: openpaper
description: >
  Generate a personalized newspaper-style digest from any news sources. Use this skill whenever the user wants to read news, set up news sources, get a daily digest, curate articles, generate a newspaper, create a morning briefing, manage their reading preferences, or says things like "make my paper", "what's new today", "add a news source", "show me the news", or "update my preferences". Also use when the user mentions OpenPaper, newspaper layout, or news curation. This skill handles the full pipeline: adding sources (writing fetchers), curating content, and rendering beautiful HTML newspaper editions.
---

# OpenPaper

A personalized newspaper that knows only you will ever read it.

Three-stage pipeline: **Ingest** (fetch news) → **Curate** (select and rank) → **Present** (render a newspaper). You are the editor-in-chief.

## Quick Reference

| Command | What it does |
|---------|-------------|
| "Make my paper" | Full pipeline: fetch → curate → render |
| "Add a source" | Analyze a URL and write a fetcher |
| "Show my preferences" | Display and edit preference profile |

## Running Scripts

All scripts use `uv run --project`. Use `${CLAUDE_PLUGIN_ROOT}` if set (plugin mode), otherwise `.` (standalone mode):

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/scripts/<script>.py <args>
```

## Data Directory

All state lives in `.openpaper/` relative to the working directory:

```
.openpaper/
├── sources/           # one .py per source (+ _base.py auto-deployed)
├── preferences.md     # user interests and feedback
├── incoming/          # raw fetched articles (JSON)
├── saved/             # archived articles from past editions
├── editions/          # rendered HTML newspapers
├── cache/             # HTTP cache for fetchers
└── seen.txt           # dedup log
```

## First Run — Setup Wizard

When `.openpaper/` doesn't exist:

### 1. Create the data directory

```bash
mkdir -p .openpaper/sources .openpaper/incoming .openpaper/saved .openpaper/editions .openpaper/cache
```

### 2. Add news sources

Say: "What do you want to read? Give me URLs, RSS feeds, or just topics." Then wait for the user's reply.

Deploy the shared base module:
```bash
cp ${CLAUDE_PLUGIN_ROOT:-.}/skills/openpaper/scripts/fetcher_base.py .openpaper/sources/_base.py
```

For each source:
1. **Analyze** — visit the URL, determine type (RSS, HTML, JS-rendered, API)
2. **Write a fetcher** — create `.openpaper/sources/<name>.py`. Read `references/fetcher-guide.md` for the interface spec and `_base.py` templates.
3. **Test** — `uv run .openpaper/sources/<name>.py --cache-dir /tmp/openpaper-test-<name>`
   > **Cache trap:** Always test with `/tmp/`, NOT `.openpaper/cache/`. Using the real cache pollutes `seen.txt` dedup.
4. **Show** the user what it found

### 3. Set preferences

Create `.openpaper/preferences.md` by chatting with the user about:
- Topics of interest and how much
- Articles per edition (default: 14, up to 18)
- Location (for weather)
- Markets data wanted?

Keep under 2000 characters. Example:

```markdown
# My Reading Preferences

## Interests
- Technology and AI (very interested)
- Software engineering (interested)
- Open source (some interest)

## Sources
Hacker News is my primary source.

## Reading Profile
~14 articles. Include weather for Oslo.

## Feedback
```

### 4. Generate first edition

Run the full pipeline and open in browser.

## Making a Paper

### Stage 1: Ingest

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/scripts/fetch_all.py --data-dir .openpaper
```

Discovers all fetchers in `.openpaper/sources/`, runs in parallel, deduplicates against `seen.txt`, fetches content, writes new articles to `.openpaper/incoming/`.

### Stage 2: Curate

> **Gate:** Only begin after Stage 1 completes and weather/markets data is collected. Curation needs the full candidate pool.

Read `references/curation-guide.md` for the full process. Summary:

1. **Inspect the pool:**
   - `uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/scripts/pool.py --data-dir .openpaper stats`
   - `uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/scripts/pool.py --data-dir .openpaper list --sort points`
   - `uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/scripts/pool.py --data-dir .openpaper show <slug>`
2. **Read** `.openpaper/preferences.md`
3. **Score and rank** articles against user interests
4. **Select** articles (typically 10-18), enforce topic/source diversity
5. **Assign editorial weight** — lead (1), major/lg (2-3), mid/md (3-5), briefs (4-8)
6. **Summarize in parallel** — spawn one subagent per article via `parallel()`:

```
parallel([
  () => agent("Summarize this lead article: <JSON>. Write 3-4 paragraphs, deck, photo_caption..."),
  () => agent("Summarize this lg article: <JSON>. Write 2 paragraphs..."),
  () => agent("Write a brief for: <JSON>. Return bold + one sentence..."),
  ...
])
```

7. **Assemble edition YAML** — see `references/edition-schema.md` for the schema

Write the YAML to `.openpaper/editions/draft.yaml`.

### Stage 2.5: Archive

1. `mkdir -p .openpaper/saved/<date>-<edition_name>`
2. Move selected article JSONs to the archive
3. Delete remaining from `.openpaper/incoming/`

### Stage 3: Present

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/scripts/render.py --data-dir .openpaper --edition .openpaper/editions/draft.yaml
```

Then preview:
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/scripts/serve.py --data-dir .openpaper --latest
```

Open in browser. Say: "Here's your paper — let me know what you think."

## Adding a Source

1. Visit the URL (screenshot or fetch)
2. Determine type: RSS, HTML, JS-rendered, API
3. Read `references/fetcher-guide.md` for the contract and `_base.py` templates
4. Write `.openpaper/sources/<name>.py`
5. Test with `/tmp/` cache dir (not the real one)
6. Show results to the user

**Key rules:**
- RSS/API first, Playwright for everything else — never use httpx for web pages
- Each fetcher is standalone with PEP 723 inline dependencies
- Must detect and exclude paywalled articles (see `_base.py` `detect_paywall`)

## Feedback Loop

After the user reads their paper, update `.openpaper/preferences.md`:
- **"More like this"** → boost topic weight
- **"Less of this"** → reduce weight
- **"Love this"** → strong positive, add to interests
- **"Hide this source"** → exclusion list
- Free-text notes → add verbatim to Feedback section

## Bundled Data Fetchers

### Weather (yr.no)
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/fetchers/weather.py \
  --lat 59.91 --lon 10.75 --location-name "Oslo, Norway" \
  --cache-dir .openpaper/cache/weather
```

### Markets (Yahoo Finance)
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT:-.} skills/openpaper/fetchers/markets.py \
  --cache-dir .openpaper/cache/markets
```

Default symbols: Oslo Børs, USD/NOK, S&P 500, Gold, Bitcoin, Brent. Override with `--symbols` and `--names`.

## Edition Schema

See `references/edition-schema.md` for the full schema. Key points:
- Stories use `section: "col1"` (string), not `column: 1` (integer)
- Story sizes: `sm`, `md`, `lg`
- Every article should include a `url` field for the original source
- Lead and `lg` stories can include `image_url` — only from fetcher data, never fabricated

## Script Reference

| Script | Purpose | Key flags |
|--------|---------|-----------|
| `fetch_all.py` | Run all source fetchers | `--data-dir`, `--source`, `--parallel` |
| `render.py` | HTML from edition YAML | `--data-dir`, `--edition`, `--output` |
| `serve.py` | Preview server | `--data-dir`, `--port`, `--latest` |
| `pool.py` | Inspect article pool | `--data-dir` + subcommands: `stats`, `list`, `show` |
