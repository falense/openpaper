# Curation Guide

How Claude curates articles and composes an edition in OpenPaper.

---

## Overview

Curation is the second stage of the OpenPaper pipeline. After fetchers have gathered raw articles from all configured sources, Claude reads the user's preference profile, scores and selects articles, and assembles an edition — a structured document that maps articles to layout slots in a newspaper template.

This guide defines the preference system, the curation algorithm, the feedback loop, and the edition schema that feeds into the rendering step.

---

## preferences.md

The user's reading profile lives at `.openpaper/preferences.md`. This file is the single source of truth for what the user cares about. It is freeform markdown read by the AI during curation — no scripts parse it.

### Reading the preference file

The preference file is written in natural language. When reading it, extract:

1. **Interests and weights.** The user expresses interest levels through natural language. Map these to approximate weights for scoring:
   - "very interested", "essential", "always" -> ~0.9
   - "interested", "like", "enjoy" -> ~0.7
   - "some interest", "occasionally" -> ~0.5
   - "passing interest", "sometimes" -> ~0.3
   - Topics not mentioned -> 0.0 (neutral, not excluded)

2. **Source preferences.** The user may name sources in priority order or describe them ("my primary source", "I also read...", "sometimes check..."). Infer priority order from the language.

3. **Reading profile.** Look for article count, target reading time, location (for weather), and market tickers.

4. **Feedback history.** The Feedback section accumulates notes from past editions. Interpret these the same way as the feedback signals described later in this guide.

### Example

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
- 2026-06-04: "AI Policy Update" — more like this. I follow AI governance closely.
- 2026-06-03: "Celebrity Gossip Roundup" — less of this.
- 2026-06-02: "Open Source Security Report" — love this. Exactly what I want to read every day.
- 2026-06-01: "Crypto Price Predictions" — hide. Never show crypto speculation.
```

### Size constraint

Keep `preferences.md` under 2000 characters. It must fit comfortably in the AI's context window alongside the article pool. If the file grows too long (e.g., from accumulated feedback), summarize older feedback into permanent interest adjustments and trim the Feedback section.

---

## Curation process

Given a pool of fetched articles and the user's preferences, follow these steps to produce an edition.

### Step 1: Score articles by relevance

For each article, compute a relevance score by matching its content against the user's interests:

1. **Topic matching.** Compare the article's title, summary, and content against the interests listed in `preferences.md`. This is a semantic match, not keyword-only — "EU digital regulation" should match "public technology" and "AI governance."

2. **Weight application.** Multiply the match strength by the inferred weight for that interest (derived from the user's language — see the weight mapping in the preferences.md section above). An article can match multiple interests; sum the weighted scores.

3. **Source priority bonus.** Articles from higher-priority sources get a small boost. Infer source priority from the user's language in `preferences.md` (e.g., "primary source" = position 1):
   - Position 1: +0.15
   - Position 2: +0.10
   - Position 3: +0.05
   - Position 4+: +0.02
   - Unlisted sources: no bonus (but no penalty either)

4. **Feedback adjustment.** Apply feedback signals:
   - `love` on a matching topic: multiply that topic's weight by 1.5
   - `more` on a matching topic: multiply by 1.2
   - `less` on a matching topic: multiply by 0.5
   - `hide` on a matching topic or source: set score to -1 (exclude entirely)

5. **Recency bonus.** Articles from today get a +0.1 boost. Yesterday gets +0.05. Older articles get no bonus.

6. **Feedback decay.** Feedback entries older than 30 days carry half weight. Older than 90 days, quarter weight.

The result is a scored, sorted list of candidate articles.

### Step 2: Diversify across topics

A newspaper is boring if every article is about the same thing. After scoring:

1. Group candidates by their primary topic match.
2. Enforce a **topic cap**: no single topic should take more than 30% of `max_articles` (rounded up). For a 14-article broadsheet, that means no more than 5 articles on one topic.
3. If a topic is over the cap, keep only its top-scoring articles and push the rest below the selection threshold.
4. If there are fewer than 3 distinct topics in the top articles, pull in the highest-scoring articles from underrepresented topics — even if their raw score is lower.

### Step 3: Balance familiar sources with discovery

Readers have preferred sources, but a good newspaper surprises.

1. Reserve at least 20% of slots for articles from sources **not** in `sources_priority` (if available). This introduces serendipity.
2. No single source should take more than 40% of articles.
3. If the candidate pool is too homogeneous (dominated by one source), explicitly seek high-scoring articles from other sources.

### Step 4: Assign editorial weight

Not all articles are equal. Decide the editorial role of each selected article:

| Role     | Size | Count per edition | Characteristics                                   |
| -------- | ---- | ----------------- | ------------------------------------------------- |
| **Lead** | xl   | 1                 | Highest combined score + recency. Gets the hero slot with photo placeholder, large headline, deck, and drop cap. |
| **Major**| lg   | 2-3               | High relevance, strong headlines. Multi-paragraph with byline. |
| **Mid**  | md   | 3-5               | Solid relevance. One or two paragraphs.            |
| **Brief**| sm   | 4-8               | Lower relevance or older. Title + one-line summary only. |

Rules for assignment:

- The **lead** article should have broad appeal (matches multiple interests or is a major event) and be from today if possible.
- **Major** articles should cover different topics from each other and from the lead.
- **Briefs** are for rounding out topic coverage without taking space. Use them for topics the user has moderate interest in.
- If `reading_time_minutes` is low (under 15), shift the balance toward more briefs and fewer majors.
- If `reading_time_minutes` is high (over 25), include more full-text majors and fewer briefs.

### Step 5: Fill the template slots

Map the selected articles into the template's layout grid. The slot assignment depends on the template:

#### Broadsheet template (14 articles)

```
+----------------------------------------------------------+
| MASTHEAD                                                  |
+----------------------------------------------------------+
| LEAD (xl)          | LEAD continued     | SIDEBAR         |
| with hero image    | + deck + body      | Weather          |
| placeholder        |                    | Markets          |
+--------------------+--------------------+-----------------+
| Major 1 (lg)       | Major 2 (lg)       | Major 3 (lg)    |
| col 1-2            | col 3-4            | col 5-6         |
+--------------------+--------------------+-----------------+
| Mid 1 (md)  | Mid 2 (md)  | Mid 3 (md)  | Briefs column   |
| col 1-2     | col 3-4     | col 5       | Brief 1-6       |
+-------------+-------------+-------------+-----------------+
```

Stories are rendered in the order they appear in the YAML array — most important stories first. CSS multi-column layout distributes them across columns automatically.

### Annotation

Every article in the edition gets a brief annotation explaining **why it was selected**. This builds trust and helps the user refine their preferences.

Good annotations:
- "because you follow Public Technology"
- "trending on Hacker News, matches your AI governance interest"
- "from NRK, your top source"
- "discovery: outside your usual topics, but the highest-scoring environment story today"

Bad annotations:
- "selected by algorithm" (too vague)
- "score: 0.87" (exposes internals the user does not care about)

---

## Feedback signals

Users refine their newspaper over time by giving feedback on articles. The agent records feedback in the `## Feedback` section of `preferences.md`.

### Signal definitions

| Signal  | Meaning                                   | Effect on preferences                           |
| ------- | ----------------------------------------- | ----------------------------------------------- |
| `more`  | "Show me more like this"                  | Boost matching topic weight by 1.2x             |
| `less`  | "I'm not interested in this"              | Reduce matching topic weight by 0.5x            |
| `love`  | "This is exactly what I want"             | Boost matching topic by 1.5x, boost source      |
| `hide`  | "Never show this again"                   | Blacklist source or topic permanently            |

### Free-text notes

Feedback entries often include nuance that simple signal words cannot express:

```
- 2026-06-04: "City Council Votes on Transit Plan" — more like this. I care about Oslo transit specifically, not all city politics.
```

When a note is present, Claude should interpret it and apply it contextually — in this case, boosting "Oslo transit" without broadly boosting "city politics."

### Applying feedback over time

1. **Append, never overwrite.** New feedback is appended to the Feedback section. The full history is preserved.
2. **Recency matters.** Recent feedback carries more weight than old feedback. See decay rules in Step 1 above.
3. **Contradictions resolve to the latest.** If the user said "more" about climate on June 1 and "less" on June 4, the June 4 signal wins.
4. **Periodic cleanup.** When the Feedback section grows long, summarize old entries into permanent interest adjustments in the Interests section, then trim the feedback. Keep `preferences.md` under 2000 characters.

### When to prompt for feedback

Do not ask for feedback on every article. Good moments to prompt:

- After the user has read an edition (post-delivery summary)
- When the user explicitly mentions liking or disliking something
- When the topic mix has been unchanged for several editions (staleness detection)

---

## Edition schema

The curated output is a YAML document that the rendering step consumes to produce the final HTML newspaper. It lives at `.openpaper/editions/<date>-<template>.yaml` alongside the rendered `.html`.

### Full schema

```yaml
template: broadsheet
date: "Thursday, June 4, 2026"
edition_number: 12
masthead:
  title: "OpenPaper"
  tagline: "Your morning brief, curated by AI"

lead:
  article_ref: "https://example.com/article-about-public-tech"
  title: "Oslo Launches Open-Source City Platform"
  kicker: "The Lead · Public Technology"
  deck: "A new open-source infrastructure platform aims to make city services transparent and composable."
  annotation: "because you follow Public Technology"
  byline: "By Jane Doe"
  body: |
    Full article text goes here, formatted as plain text
    with paragraph breaks. The template handles typography.
  photo_alt: "Descriptive alt text for the hero image placeholder"

stories:
  - article_ref: "https://example.com/climate-policy"
    title: "Nordic Climate Pact Advances"
    size: lg
    column: 1
    kicker: "Climate"
    deck: "Five Nordic nations agree on binding emissions targets."
    annotation: "matches your Climate interest"
    byline: "By John Smith"
    body: "Article text..."

  - article_ref: "https://example.com/ai-regulation"
    title: "EU AI Act Enforcement Begins"
    size: lg
    column: 3
    kicker: "AI Governance"
    annotation: "trending, matches AI governance"
    byline: "By Ada Lovelace"
    body: "Article text..."

  - article_ref: "https://example.com/oslo-metro"
    title: "Metro Extension Breaks Ground"
    size: md
    column: 1
    kicker: "Oslo"
    annotation: "local news from your location"
    body: "Article text..."

  - article_ref: "https://example.com/open-source-funding"
    title: "Linux Foundation Doubles Grants"
    size: md
    column: 3
    kicker: "Open Source"
    annotation: "because you follow Open Source"
    body: "Article text..."

  - article_ref: "https://example.com/architecture-oslo"
    title: "New Library Design Unveiled"
    size: sm
    column: 5
    kicker: "Urban Planning"
    annotation: "discovery: related to your urban planning interest"

briefs:
  - article_ref: "https://example.com/brief-1"
    title: "Parliament Approves Budget Amendment"
    source: nrk
    annotation: "Norwegian politics, from your top source"

  - article_ref: "https://example.com/brief-2"
    title: "Rust 2.0 Released"
    source: hackernews
    annotation: "open source, trending on HN"

  - article_ref: "https://example.com/brief-3"
    title: "Arctic Ice Study Published"
    source: guardian
    annotation: "climate, from a trusted source"

  - article_ref: "https://example.com/brief-4"
    title: "Copenhagen Bike Lane Expansion"
    source: guardian
    annotation: "discovery: urban planning in a neighboring city"

weather:
  location: "Oslo, Norway"
  current:
    temp_c: 14
    condition: "Partly cloudy"
    icon: "cloud-sun"
  forecast:
    - day: "Fri"
      high_c: 16
      low_c: 9
      icon: "sun"
    - day: "Sat"
      high_c: 13
      low_c: 8
      icon: "rain"
    - day: "Sun"
      high_c: 15
      low_c: 10
      icon: "cloud"

markets:
  - name: "OBX"
    value: "1,284.50"
    change: "+0.8%"
    direction: "up"
  - name: "S&P 500"
    value: "5,892.10"
    change: "-0.3%"
    direction: "down"
  - name: "EUR/NOK"
    value: "11.42"
    change: "+0.1%"
    direction: "up"
```

### Field reference

#### Top level

| Field            | Type   | Required | Notes                                    |
| ---------------- | ------ | -------- | ---------------------------------------- |
| `template`       | `str`  | yes      | `broadsheet`                             |
| `date`           | `str`  | yes      | Human-readable date for the masthead     |
| `edition_number` | `int`  | no       | Sequential edition count                 |
| `masthead`       | `obj`  | no       | Title and tagline overrides              |

#### Lead

| Field         | Type  | Required | Notes                                       |
| ------------- | ----- | -------- | ------------------------------------------- |
| `article_ref` | `str` | yes      | URL of the source article                   |
| `title`       | `str` | yes      | Headline (may be edited for space)          |
| `kicker`      | `str` | yes      | Section label above headline                |
| `deck`        | `str` | no       | Subtitle / summary line below headline      |
| `annotation`  | `str` | yes      | Why this article was selected               |
| `byline`      | `str` | no       | Author attribution                          |
| `body`        | `str` | yes      | Full article text                           |
| `photo_alt`   | `str` | no       | Alt text describing the photo placeholder   |

#### Stories

| Field         | Type  | Required | Notes                                            |
| ------------- | ----- | -------- | ------------------------------------------------ |
| `article_ref` | `str` | yes      | URL of the source article                        |
| `title`       | `str` | yes      | Headline                                         |
| `size`        | `str` | yes      | `lg`, `md`, or `sm`                              |
| `kicker`      | `str` | no       | Section label                                    |
| `deck`        | `str` | no       | Subtitle (usually only for `lg`)                 |
| `annotation`  | `str` | yes      | Why selected                                     |
| `byline`      | `str` | no       | Author                                           |
| `body`        | `str` | no       | Article text (required for `lg` and `md`)        |

#### Briefs

| Field         | Type  | Required | Notes                           |
| ------------- | ----- | -------- | ------------------------------- |
| `article_ref` | `str` | yes      | URL                             |
| `title`       | `str` | yes      | Headline (one line)             |
| `source`      | `str` | no       | Source slug for attribution     |
| `annotation`  | `str` | yes      | Why selected                    |

#### Weather

| Field                  | Type   | Required | Notes                    |
| ---------------------- | ------ | -------- | ------------------------ |
| `location`             | `str`  | yes      | Display name             |
| `current.temp_c`       | `int`  | yes      | Temperature in Celsius   |
| `current.condition`    | `str`  | yes      | Text description         |
| `current.icon`         | `str`  | yes      | Icon key for the template|
| `forecast[].day`       | `str`  | yes      | Abbreviated day name     |
| `forecast[].high_c`    | `int`  | yes      | High temperature         |
| `forecast[].low_c`     | `int`  | yes      | Low temperature          |
| `forecast[].icon`      | `str`  | yes      | Icon key                 |

#### Markets

| Field       | Type  | Required | Notes                         |
| ----------- | ----- | -------- | ----------------------------- |
| `name`      | `str` | yes      | Index or ticker name          |
| `value`     | `str` | yes      | Current value (formatted)     |
| `change`    | `str` | yes      | Change with sign ("+0.8%")    |
| `direction` | `str` | yes      | `up` or `down`                |

---

## Putting it all together: curation walkthrough

Here is a concrete example of the curation process from start to finish.

### Input

- 47 articles fetched from 4 sources (nrk: 12, hackernews: 15, guardian: 10, techcrunch: 10)
- User wants a broadsheet with 14 articles
- User interests: public technology (0.9), climate (0.7), Norwegian politics (0.5), AI governance (0.8)

### Step-by-step

1. **Score all 47 articles.** Each gets a relevance score. Example scores:
   - "Oslo Launches Open-Source City Platform" (nrk) -> 0.9 (public tech) + 0.15 (nrk #1) + 0.1 (today) = 1.15
   - "Celebrity Chef Opens Restaurant" (nrk) -> no topic match, 0.15 (nrk) = 0.15
   - "EU AI Act Enforcement" (hackernews) -> 0.8 (AI gov) + 0.10 (HN #2) + 0.1 (today) = 1.00

2. **Sort by score.** Top 20 candidates emerge. Most are public tech and AI governance.

3. **Diversify.** 8 of the top 14 are public tech. Cap at 5 (30% of 14, rounded up). Bump the 3 weakest public tech articles down, pull in the top climate and Norwegian politics articles instead.

4. **Source balance.** Check: nrk has 6 of 14 (43%). Cap at 40% = 5. Drop the lowest-scoring nrk article, pull in the top guardian article.

5. **Discovery.** Only 1 of 14 is from outside `sources_priority`. Reserve 20% = 3 slots. Pull in 2 more articles from unlisted sources that scored well.

6. **Assign roles:**
   - Lead: "Oslo Launches Open-Source City Platform" (highest score, today, broad appeal)
   - Major: "EU AI Act Enforcement", "Nordic Climate Pact", "Parliament Budget Vote"
   - Mid: 4 articles covering AI, open source, urban planning, local news
   - Brief: 6 articles rounding out remaining topics

7. **Map to template slots.** Lead goes to the hero position. Majors fill the three column slots below. Mids and briefs fill the lower grid.

8. **Write annotations.** Each article gets a one-line reason.

9. **Emit the edition YAML.** The rendering step takes it from here.

10. **Archive and clean up.** Move selected articles to `saved/` and clear `incoming/`. See the Archiving section below.

---

## Archiving curated articles

After assembling the edition YAML, archive the curated articles for future reference. This builds a permanent record of what the user has been shown, enabling better deduplication and preference learning over time.

### Procedure

1. **Create an edition subfolder** under `.openpaper/saved/` named after the edition (e.g., `2026-06-04-morning`). Use the pattern `<date>-<edition-name>`.

2. **Move selected articles** from `.openpaper/incoming/` into the edition subfolder. These are the articles referenced in the edition YAML — lead, stories, and briefs. Keep the original JSON filenames.

3. **Delete remaining articles** from `.openpaper/incoming/`. Articles that were not selected have already been logged in `seen.txt` by the fetcher, so they will not be re-fetched. They do not need to be preserved.

4. **Verify `incoming/` is empty** after cleanup. The next fetch cycle will populate it with fresh articles.

### Using the archive in future curation

When curating a new edition, check `.openpaper/saved/` to:

- **Avoid repeating stories.** If a story (by URL or topic) appeared in a recent edition, do not select it again unless there is a meaningful update.
- **Track topic trends.** Browsing past editions reveals what the user has been reading heavily — useful for adjusting the discovery/familiarity balance.
- **Correlate with feedback.** When the user gives feedback on an article, the archived copy provides full context for interpreting the signal.

### Housekeeping

The `saved/` directory grows over time. No automatic cleanup is needed — editions are small (10-18 JSON files each). If disk space becomes a concern, the oldest edition folders can be removed manually.

---

## Edge cases

### Paywalled articles filtered upstream

Articles without full content are filtered at the fetch stage — they never reach curation. If the article pool is small as a result, reduce the edition size gracefully rather than lowering content standards.

### Not enough articles

If fetchers return fewer articles than `max_articles`, reduce the edition gracefully:
- Keep the lead and at least 2 majors
- Convert remaining to mids and briefs
- Never pad with irrelevant articles just to fill slots

### All articles are from one topic

If 90%+ of fetched articles match a single topic (breaking news day), allow the topic cap to expand to 50% but still fill remaining slots with other topics if any exist. Add a kicker like "Special Report" to acknowledge the focus.

### No feedback yet

For a new user with no feedback history, rely solely on the interest weights and source priority. The first few editions will be exploratory. Prompt for feedback after the second edition.

### Conflicting feedback

If the user gave "love" to an article about AI last week and "less" to a different AI article today, interpret contextually using the notes. If there are no notes, the latest signal wins for scoring purposes, but do not zero out the topic — reduce it moderately.

---

## Template reference

The broadsheet template and its slot counts:

| Template    | Total articles | Lead | Major (lg) | Mid (md) | Brief (sm) | Has weather | Has markets |
| ----------- | -------------- | ---- | ---------- | -------- | ---------- | ----------- | ----------- |
| broadsheet  | 10-18          | 1    | 2-3        | 3-5      | 4-8        | yes         | yes         |

The broadsheet is a responsive template (375px mobile through 1960px spread) with a classic newspaper feel: cream paper, blackletter masthead, serif body text, handwritten margin annotations. Stories flow via CSS multi-column layout — the article count is flexible.

It uses the shared assets (`magic.css`, `magic.js`) for paper grain, halftone effects, ink-draw headline animations, and weather glyphs.

---

## Image handling

Fetchers extract `image_url` (og:image / twitter:image) from article pages. These flow through the pipeline into the edition YAML and are rendered with a newspaper halftone effect.

### Rules

1. **Never fabricate image URLs.** Only use `image_url` values that came from the fetcher's article data. Do not guess URL patterns, resize parameters, or CDN paths.
2. **Lead image.** The lead story should use `image_url` when the fetcher provided one. If no image is available, the template falls back to a generated scene.
3. **Story images.** `lg`-sized stories benefit most from images — include `image_url` when available. `md`-sized stories can optionally have images if the column has room. `sm` stories and briefs do not use images.
4. **Match image to article.** Verify that the image belongs to the article it's assigned to. Do not reuse one article's image on a different story.
5. **Missing images are fine.** Not every story needs an image. The templates handle the absence gracefully — no broken layout, no placeholder boxes.

