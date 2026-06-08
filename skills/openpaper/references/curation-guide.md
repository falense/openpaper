# Curation Guide

How to curate articles and compose an edition.

---

## Overview

Curation is Stage 2 of the pipeline. After fetchers gather articles, read the user's `preferences.md`, score and select articles, and assemble the edition YAML for rendering.

---

## preferences.md

The user's reading profile at `.openpaper/preferences.md` is freeform markdown. Extract:

1. **Interests and weights** — map language to priority: "very interested" → high, "some interest" → moderate, "passing interest" → low
2. **Source preferences** — infer priority from language ("primary source" > "I also read" > "sometimes check")
3. **Reading profile** — article count, reading time, location, market tickers
4. **Feedback history** — accumulated signals from past editions

Keep `preferences.md` under 2000 characters. If it grows too long, summarize older feedback into permanent interest adjustments.

---

## Curation process

### Step 1: Score articles

For each article, evaluate relevance by matching against user interests:

- **Topic relevance**: Semantic match against stated interests (not just keywords)
- **Source priority**: Higher-priority sources get a boost
- **Recency**: Today's articles rank higher
- **Feedback signals**: Apply accumulated feedback (love → 1.5x boost, more → 1.2x, less → 0.5x, hide → exclude)

### Step 2: Diversify

- **Topic cap**: No single topic > 30% of articles
- **Source cap**: No single source > 40%
- **Discovery**: Reserve ~20% for articles outside primary interests
- Ensure at least 3 distinct topics

### Step 3: Assign editorial weight

| Role | Size | Count | Description |
|------|------|-------|-------------|
| **Lead** | xl | 1 | Highest relevance + recency. Hero slot with photo, deck, drop cap. |
| **Major** | lg | 2-3 | High relevance, different topics from each other and lead. |
| **Mid** | md | 3-5 | Solid relevance. One or two paragraphs. |
| **Brief** | sm | 4-8 | Lower relevance or older. Bold keyword + one sentence. |

### Step 4: Summarize in parallel

Spawn **one subagent per selected article** using `parallel()`. Each receives the full article JSON, its assigned role, and the matching user interest (for the annotation).

**Summary guidelines by role:**

| Role | Output |
|------|--------|
| **Lead** | 3–4 paragraphs, drop-cap opening, narrative arc. Plus `deck` and `photo_caption`. |
| **lg** | 2 paragraphs — key facts + quote/detail. Optional `deck`. |
| **md** | 1 tight paragraph — who, what, why it matters. |
| **Brief** | `bold` (source/topic keyword) + `text` (one sentence, max 15 words). |

Each subagent returns:

**Lead/lg/md:**
```json
{"paragraphs": ["..."], "deck": "subtitle", "kicker": "Topic", "photo_caption": "lead only"}
```

**Brief:**
```json
{"bold": "Topic", "text": "one sentence."}
```

If a subagent fails, drop that article and pull in the next-highest candidate.

### Step 5: Assemble edition YAML

Collect subagent results and compose the edition YAML conforming to `references/edition-schema.md`. Add annotations explaining why each article was selected:

Good: "because you follow Public Technology", "trending on HN, matches your AI interest", "discovery: outside your usual topics"

### Step 6: Archive

1. `mkdir -p .openpaper/saved/<date>-<edition_name>`
2. Move selected article JSONs from `incoming/` to the archive
3. Delete remaining unselected files from `incoming/`
4. Verify `incoming/` is empty

---

## Image handling

1. **Never fabricate image URLs** — only use `image_url` values from fetcher data
2. Lead story should use `image_url` when available; template falls back gracefully
3. `lg` stories benefit most from images; `md` optionally; `sm`/briefs do not use images
4. Match images to their articles — never reuse across stories

---

## Feedback signals

| Signal | Meaning | Effect |
|--------|---------|--------|
| `more` | "More like this" | Boost matching topic 1.2x |
| `less` | "Not interested" | Reduce matching topic 0.5x |
| `love` | "Exactly what I want" | Boost topic 1.5x + boost source |
| `hide` | "Never show this" | Blacklist source or topic |

Record feedback in `## Feedback` of `preferences.md`. Latest signal wins on contradictions. Feedback older than 30 days carries half weight; older than 90, quarter weight.

---

## Edge cases

- **Few articles**: Keep the lead + 2 majors minimum, convert rest to briefs. Never pad with irrelevant articles.
- **One dominant topic** (breaking news): Allow topic cap to expand to 50% but still fill other slots. Add a "Special Report" kicker.
- **No feedback yet**: Rely on interest weights and source priority. Prompt for feedback after the second edition.
