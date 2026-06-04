---
name: openpaper
description: >
  Generate a personalized newspaper-style digest from any news sources. Use this skill whenever the user wants to read news, set up news sources, get a daily digest, curate articles, generate a newspaper, create a morning briefing, manage their reading preferences, or says things like "make my paper", "what's new today", "add a news source", "show me the news", or "update my preferences". Also use when the user mentions OpenPaper, newspaper layout, or news curation. This skill handles the full pipeline: adding sources (writing fetchers), curating content, and rendering beautiful HTML newspaper editions.
---

# OpenPaper

A personalized newspaper that knows only you will ever read it.

OpenPaper is a three-stage pipeline: **Ingest** (fetch news), **Curate** (select and rank), **Present** (render a newspaper). You are the editor-in-chief — you make the editorial decisions about what to include and how to present it.

## Quick Reference

| Command | What it does |
|---------|-------------|
| "Make my paper" | Run the full pipeline: fetch → curate → render |
| "Add a source" | Analyze a URL and write a fetcher for it |
| "Show my preferences" | Display and edit the user's preference profile |
| "Give me feedback on today's paper" | Start the feedback loop |

## Data Directory

All user state lives in `.openpaper/` relative to the working directory:

```
.openpaper/
├── sources/           # one .py file per source (+ _base.py deployed by fetch_all)
│   ├── _base.py
│   ├── hackernews.py
│   ├── bbc.py
│   └── ...
├── preferences.md
├── incoming/          # raw fetched articles (JSON)
├── saved/             # archived articles from past editions
├── editions/          # rendered HTML newspapers
├── cache/             # HTTP cache for fetchers
└── seen.txt           # dedup log
```

## First Run — Setup Wizard

When `.openpaper/` doesn't exist, guide the user through setup:

### Step 1: Create the data directory

```bash
mkdir -p .openpaper/sources .openpaper/incoming .openpaper/saved .openpaper/editions .openpaper/cache
```

### Step 2: Ask about news sources

Ask the user: "What do you want to read? Give me URLs, RSS feeds, or just topics."

Before writing any fetchers, deploy the shared base module so imports work:

```bash
cp ${CLAUDE_PLUGIN_ROOT}/skills/openpaper/scripts/fetcher_base.py .openpaper/sources/_base.py
```

For each source the user provides:

1. **Analyze the source** — visit the URL, determine if it's RSS, static HTML, JS-rendered, or an API
2. **Write a fetcher** — create `.openpaper/sources/<name>.py` following the fetcher contract. Import from `_base` for shared utilities. Read `references/fetcher-guide.md` for the full interface spec and examples.
3. **Test the fetcher** — run it and show the user what it pulled:
   ```bash
   uv run .openpaper/sources/<name>.py --cache-dir /tmp/openpaper-test-<name>
   ```
   > **Cache trap:** Always test with `--cache-dir /tmp/openpaper-test-<name>`, NOT the real cache at `.openpaper/cache/<name>`. If you use the real cache, `fetch_all` will treat all tested articles as already seen (via `seen.txt` dedup) and return 0 new articles.
4. **Confirm with the user** — "Here are the articles I found from <source>. Does this look right?"

Repeat for each source. The user can always add more sources later.

### Step 3: Set preferences

Create `.openpaper/preferences.md` by asking the user about their interests. At minimum, ask:

- What topics interest you most?
- How many articles per edition? (default: 14, flexible up to 18)
- Location (for weather widget)
- Do you want markets data?

> **Note:** `preferences.md` is read by the AI during curation, not by scripts. Keep it under 2000 characters — enough to capture interests, source preferences, and reading profile, but concise enough to fit in context.

Example `preferences.md`:

```markdown
# My Reading Preferences

## Interests
- Technology and AI (very interested)
- Software engineering (interested)
- Open source (some interest)
- Norwegian politics (passing interest)

## Sources
Hacker News is my primary source. I also read NRK for Norwegian news.

## Reading Profile
I like ~18 articles, about 25 minutes of reading.
Include weather for Oslo and markets (Oslo Børs, USD/NOK, S&P 500, Gold, Bitcoin, Brent).

## Feedback
(Updated after each edition — the agent adds notes here)
```

### Step 4: Generate first edition

Run the full pipeline once to show the user their first paper. Open it in the browser with the preview server.

## Making a Paper

The full pipeline runs in three stages:

### Stage 1: Ingest

Run all fetchers to collect fresh articles:

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} skills/openpaper/scripts/fetch_all.py --data-dir .openpaper
```

This discovers all `.py` files in `.openpaper/sources/` (excluding `_base.py`), runs their fetchers in parallel, deduplicates against `seen.txt` automatically, and writes new articles as JSON to `.openpaper/incoming/`.

### Stage 2: Curate

This is where you act as editor-in-chief. Read `references/curation-guide.md` for the full curation process.

1. **Read the incoming articles** — scan `.openpaper/incoming/` for new articles
2. **Read user preferences** — read `.openpaper/preferences.md`
3. **Score and rank** — evaluate each article against the user's interests
4. **Select** — choose the right number of articles (typically 10-18)
5. **Assign editorial weight** — decide which story leads, which are medium features, which are briefs
6. **Compose the edition** — write an edition YAML file that maps articles to layout slots

The edition YAML structure:

```yaml
template: broadsheet
edition_name: morning
date: "Thursday, June 4, 2026"
date_formal: "Thursday, the Fourth of June, MMXXVI"
volume: auto
number: auto
location: "Oslo, Norway"
reading_time: "22 min"
article_count: 14
tagline: "All the news that fits the day you are about to have."
printed_time: "06:14 CET"

weather:
  icon: cloud
  temp: 14
  description: "Overcast, clearing by noon"
  high: 17
  low: 9
  wind: "NW 8 km/h"
  forecast:
    - {day: FRI, temp: 18}
    - {day: SAT, temp: 21}
    - {day: SUN, temp: 19}
    - {day: MON, temp: 16}

markets:
  - {name: "Oslo Børs", value: "1,486", change: "+0.6%", direction: up}
  - {name: "USD/NOK", value: "10.42", change: "−0.3%", direction: down}
  - {name: "S&P 500", value: "5,892", change: "+0.4%", direction: up}
  - {name: Gold, value: "2,680", change: "+0.2%", direction: up}
  - {name: Bitcoin, value: "108,450", change: "+1.8%", direction: up}
  - {name: Brent, value: "72.30", change: "−1.1%", direction: down}

lead:
  kicker: "The Lead · Public Technology"
  title: "A Newspaper That Knows Only You Will Ever Read It"
  deck: "Personalised journalism leaves the laboratory..."
  byline: "By the OpenPaper Desk · Filed 06:14 in Oslo"
  paragraphs:
    - "The spread you are reading..."
    - "Proponents argue that..."
  annotation: "because you follow Public Technology"
  photo_caption: "First light over the harbour..."

stories:
  - kicker: Climate
    title: "Fjord Hits a Record..."
    paragraphs: ["Marine stations..."]
    size: lg
    has_thumb: true
  - kicker: "City Hall"
    title: "A Budget Written in Public"
    paragraphs: ["Every line of the coming..."]
    size: lg

briefs:
  - {bold: Oslo, text: "moves to publish the source of every algorithm it runs."}
  - {bold: Krone, text: "steadies after a volatile week."}

sections_index:
  - {name: Public Tech, page: A2}
  - {name: "Science & Climate", page: A6}

word_of_day:
  word: Petrichor
  definition: "the scent of first rain"
```

Write this YAML to a temporary file (e.g., `.openpaper/editions/draft.yaml`).

### Stage 2.5: Archive

After writing the edition YAML, archive selected articles and clean up incoming:

1. `mkdir -p .openpaper/saved/<date>-<edition_name>` (e.g., `2026-06-04-morning`)
2. Move JSON files for selected articles into the archive folder
3. Delete remaining unselected files from `.openpaper/incoming/`
4. Verify `.openpaper/incoming/` is empty

This keeps a record of past editions and prevents stale articles from accumulating.

**Important editorial guidelines:**
- The lead story should be the most relevant AND most interesting article
- Balance topics — don't let one category dominate
- Briefs should be genuinely brief — one sentence each
- The annotation explains WHY this story was chosen (ties to user interests)
- Weather and markets should use real data if available, or sensible placeholders
- **Images:** Use `image_url` values from the fetcher's article data. Never fabricate or guess image URLs. The lead and `lg` stories benefit most from images. See `references/curation-guide.md` for full rules.

### Stage 3: Present

Render the edition YAML into HTML:

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} skills/openpaper/scripts/render.py --data-dir .openpaper --edition .openpaper/editions/draft.yaml
```

Then serve it for preview:

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} skills/openpaper/scripts/serve.py --data-dir .openpaper --latest
```

Open the URL in the user's browser and ask for feedback.

## Adding a Source

When the user says "add <url> as a source":

1. Visit the URL (use the screenshot skill or fetch it directly)
2. Determine the source type: RSS, static HTML, JS-rendered, or API
3. Read `references/fetcher-guide.md` for the fetcher contract and examples
4. Write the fetcher: `.openpaper/sources/<name>.py` — import helpers from `_base`
5. Test it: `uv run .openpaper/sources/<name>.py --cache-dir /tmp/openpaper-test-<name>`
   > Use `/tmp/` for testing — not the real cache. See the cache trap warning above.
6. Show the user what it found and confirm

When writing fetchers:
- **RSS/API first, Playwright for everything else** — never use httpx to fetch web pages
  - RSS sources: use `feedparser` + `urllib.request` for the feed, Playwright for article content
  - HTML listing sources: use Playwright for both listing and content (one browser instance)
  - API sources: use `httpx` only for machine-readable JSON/XML APIs, Playwright for article content
- Each fetcher must be standalone with PEP 723 inline dependencies
- Output JSON array to stdout, errors to stderr
- Fetchers must detect and exclude paywalled articles — see `references/fetcher-guide.md` for the `detect_paywall` reference implementation
- Handle failures gracefully — return partial results, never crash
- Requires `playwright install chromium` in the environment

## Feedback Loop

After the user reads their paper, ask for feedback. Update `.openpaper/preferences.md` based on their signals:

- **"More like this"** → increase weight for the article's topic/source
- **"Less of this"** → decrease weight
- **"Love this"** → strong positive signal, add to interests
- **"Hide this source"** → add to exclusion list
- Free-text notes → add verbatim to the Feedback section

The preference file accumulates feedback over time. Each edition should get slightly better at matching the user's interests.

## Repairing Broken Fetchers

Fetchers can break when sites change their layout. When a fetcher fails:

1. Check the error output
2. Visit the source URL to see what changed
3. Rewrite the fetcher to handle the new structure
4. Test and confirm with the user

## Templates

One responsive template is available in `${CLAUDE_PLUGIN_ROOT}/skills/openpaper/templates/`:

- **broadsheet.html.j2** — responsive layout (375px mobile through 1960px spread), CSS multi-column story grid, feature lead story with photo

It uses:
- UnifrakturCook blackletter for the masthead
- Newsreader/PT Serif for headlines and body
- Animated paper grain, halftone photo effects, ink-draw headline reveals
- Responsive weather and markets widgets

The user can also ask for completely custom output formats — plain text, markdown, email-friendly HTML, PDF, etc. For custom formats, compose the output directly rather than using the templates.

## Bundled Data Fetchers

The plugin ships with infrastructure fetchers for weather and markets. Run these during curation and paste their output into the edition YAML.

### Weather (yr.no)

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} skills/openpaper/fetchers/weather.py \
  --lat 59.91 --lon 10.75 --location-name "Oslo, Norway" \
  --cache-dir .openpaper/cache/weather
```

Outputs JSON matching the edition `weather` sub-schema. Uses the free yr.no locationforecast API. Caches for 1 hour.

### Markets (Yahoo Finance)

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} skills/openpaper/fetchers/markets.py \
  --cache-dir .openpaper/cache/markets
```

Default symbols: Oslo Børs, USD/NOK, S&P 500, Gold, Bitcoin, Brent. Override with `--symbols` and `--names`. Outputs JSON array matching the edition `markets` sub-schema. Caches for 15 minutes.

## Edition Schema

The edition YAML must conform to the schema in `references/edition-schema.md`. Key points:

- Stories are rendered in array order using CSS multi-column layout — most important first
- Story sizes: sm/md/lg
- Every article should include a `url` field linking to the original source
- The lead and stories can include `image_url` for real article images (grayscale + halftone applied automatically). Only use URLs extracted by the fetcher — never fabricate or guess image URLs

## Script Reference

All scripts use PEP 723 inline dependencies and run via `uv run`:

| Script | Purpose | Key flags |
|--------|---------|-----------|
| `fetch_all.py` | Run all source fetchers | `--data-dir`, `--source`, `--parallel` |
| `render.py` | Generate HTML from edition YAML | `--data-dir`, `--edition`, `--output` |
| `serve.py` | Preview server for editions | `--data-dir`, `--port`, `--latest` |

Always use `--project ${CLAUDE_PLUGIN_ROOT}` when running scripts to keep the working directory correct:

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} skills/openpaper/scripts/<script>.py <args>
```
