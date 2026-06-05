# Edition YAML Schema

Canonical reference for the edition YAML that drives OpenPaper's Jinja2 templates.
This document is the single source of truth — when it conflicts with other docs, this wins.

---

## Key convention: `section`, not `column`

Stories use `story.section` with string values (`"col1"`, `"col2"`, etc.), **not** `story.column` with integers.

---

## Top-level fields

| Field | Type | Required | Example |
|-------|------|----------|---------|
| `template` | string | **yes** | `"broadsheet"` |
| `edition_name` | string | **yes** | `"morning"` |
| `date` | string | **yes** | `"Thursday, June 4, 2026"` |
| `date_formal` | string | optional | `"Thursday, the Fourth of June, MMXXVI"` |
| `volume` | string | **yes** | `"MMXXVI"` or `"auto"` |
| `number` | string | **yes** | `"156"` or `"auto"` |
| `location` | string | **yes** | `"Oslo, Norway"` |
| `reading_time` | string | **yes** | `"22 min"` |
| `article_count` | int | **yes** | `14` |
| `tagline` | string | **yes** | `"All the news that fits the day you are about to have."` |
| `printed_time` | string | **yes** | `"06:14 CET"` |

---

## `weather`

| Field | Type | Required | Example |
|-------|------|----------|---------|
| `icon` | string | **yes** | `"cloud"`, `"sun"`, `"rain"`, `"snow"` |
| `temp` | int | **yes** | `14` |
| `description` | string | **yes** | `"Overcast, clearing by noon"` |
| `high` | int | **yes** | `17` |
| `low` | int | **yes** | `9` |
| `wind` | string | **yes** | `"NW 8 km/h"` |
| `forecast` | array | **yes** | `[{day: FRI, temp: 18}, ...]` |

`forecast[]` items: `day` (string, e.g. `"FRI"`) + `temp` (int).

---

## `markets[]`

| Field | Type | Required | Example |
|-------|------|----------|---------|
| `name` | string | **yes** | `"OSEBX"` |
| `value` | string | **yes** | `"1,486"` |
| `change` | string | **yes** | `"+0.6%"` |
| `direction` | string | **yes** | `"up"` or `"down"` |

---

## `lead`

| Field | Type | Required |
|-------|------|----------|
| `kicker` | string | **yes** |
| `title` | string | **yes** |
| `deck` | string | **yes** |
| `byline` | string | **yes** |
| `paragraphs` | array[string] | **yes** |
| `annotation` | string | **yes** |
| `photo_caption` | string | **yes** |
| `url` | string | no |
| `image_url` | string | no |

Use `\n` in title to split across lines (each becomes `<span class="ink-line">`). The annotation is a handwritten margin note explaining why this story was chosen.

---

## `stories[]`

| Field | Type | Required |
|-------|------|----------|
| `kicker` | string | **yes** |
| `title` | string | **yes** |
| `paragraphs` | array[string] | **yes** |
| `size` | string | **yes** |
| `section` | string | **yes** |
| `has_thumb` | bool | no |
| `url` | string | no |
| `image_url` | string | no |

**Sizes:** `sm` (14px), `md` (17px), `lg` (22px)

**Sections:** `col1` through `col5` (6-column grid; col6 is the weather/markets rail).

---

## `briefs[]`

| Field | Type | Required |
|-------|------|----------|
| `bold` | string | **yes** |
| `text` | string | **yes** |
| `url` | string | no |

Rendered as a bulleted list at the top of column 1.

---

## `sections_index[]`

| Field | Type | Required | Example |
|-------|------|----------|---------|
| `name` | string | **yes** | `"Public Tech"` |
| `page` | string | **yes** | `"A2"` |

---

## `word_of_day`

| Field | Type | Required |
|-------|------|----------|
| `word` | string | **yes** |
| `definition` | string | **yes** |

---

## Slot budget (14 articles typical)

| Slot | Count | Populated by |
|------|-------|-------------|
| Lead | 1 | `lead` object |
| Stories (col1-5) | ~8-10 | `stories[]` array |
| Briefs | ~5-7 | `briefs[]` array |
| Weather | 1 box | `weather` object (col6) |
| Markets | 1 box | `markets[]` array (col6) |
| Inside Today | 1 box | `sections_index[]` (col6) |
| Word of Day | 1 | `word_of_day` (footer) |

Column distribution: col1 (briefs + 1-2 stories), col2-5 (2-3 stories each), col6 (weather/markets/index rail only).

---

## Validation checklist

- [ ] `template` is `"broadsheet"`
- [ ] All top-level fields present (`volume`/`number` can be `"auto"`)
- [ ] `weather` has `icon`, `temp`, `description`, `high`, `low`, `wind`, `forecast[]`
- [ ] `weather.icon` is one of: `cloud`, `sun`, `rain`, `snow`
- [ ] `lead` has `kicker`, `title`, `deck`, `byline`, `paragraphs`, `annotation`, `photo_caption`
- [ ] All `stories[]` have `kicker`, `title`, `paragraphs`, `size`, `section`
- [ ] Story sizes are `sm`, `md`, or `lg`
- [ ] Story sections are string values `"col1"` through `"col5"` (not integers, not `col6`)
- [ ] All `briefs[]` have `bold` and `text`
- [ ] `sections_index[]` items have `name` and `page`
- [ ] `word_of_day` has `word` and `definition`
