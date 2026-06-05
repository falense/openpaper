# Edition YAML Schema

Canonical reference for the edition YAML files that drive OpenPaper's Jinja2 templates.
This document is the single source of truth. When it conflicts with other docs, this wins.

---

## Key convention: `section`, not `column`

Templates use `story.section` with string values (`"col1"`, `"col2"`, etc.), **not** `story.column` with integers. The curation guide's `column: 1` examples are outdated. Always use `section: "col1"`.

---

## Top-level fields

| Field            | Type   | Required        | Example                                        | Notes |
|------------------|--------|-----------------|------------------------------------------------|-------|
| `template`       | string | **yes**         | `"broadsheet"`                                 | Selects the Jinja2 template |
| `edition_name`   | string | **yes**         | `"morning"`                                    | Used in output filename |
| `date`           | string | **yes**         | `"Thursday, June 4, 2026"`                     | Human-readable, appears in dateline |
| `date_formal`    | string | optional        | `"Thursday, the Fourth of June, MMXXVI"`       | Alternative formal dateline |
| `volume`         | string | **yes**         | `"MMXXVI"` or `"auto"`                         | Roman numeral year; `"auto"` uses current year |
| `number`         | string | **yes**         | `"156"` or `"auto"`                            | Issue number; `"auto"` increments from previous editions |
| `location`       | string | **yes**         | `"Oslo, Norway"`                               | Appears in dateline |
| `reading_time`   | string | **yes**         | `"22 min"`                                     | Displayed in dateline |
| `article_count`  | int    | **yes**         | `14`                                           | Shown in header bar |
| `tagline`        | string | **yes**         | `"All the news that fits the day you are about to have."` | Displayed in left flank |
| `printed_time`   | string | **yes**         | `"06:14 CET"`                                  | Footer timestamp |

---

## `weather`

| Field         | Type   | Required | Example                          |
|---------------|--------|----------|----------------------------------|
| `icon`        | string | **yes**  | `"cloud"`, `"sun"`, `"rain"`, `"snow"` |
| `temp`        | int    | **yes**  | `14`                             |
| `description` | string | **yes**  | `"Overcast, clearing by noon"`   |
| `high`        | int    | **yes**  | `17`                             |
| `low`         | int    | **yes**  | `9`                              |
| `wind`        | string | **yes**  | `"NW 8 km/h"`                   |
| `forecast`    | array  | **yes**  | see below                        |

### `weather.forecast[]`

| Field  | Type   | Required | Example |
|--------|--------|----------|---------|
| `day`  | string | **yes**  | `"FRI"` |
| `temp` | int    | **yes**  | `18`    |

Rendered in the weather box in column 6 (the right rail).

---

## `markets[]`

| Field       | Type   | Required | Example         |
|-------------|--------|----------|-----------------|
| `name`      | string | **yes**  | `"OSEBX"`       |
| `value`     | string | **yes**  | `"1,486"`       |
| `change`    | string | **yes**  | `"+0.6%"`       |
| `direction` | string | **yes**  | `"up"` or `"down"` |

Rendered in a box in column 6.

---

## `lead`

| Field           | Type          | Required | Example |
|-----------------|---------------|----------|---------|
| `kicker`        | string        | **yes**  | `"The Lead · Public Technology"` |
| `title`         | string        | **yes**  | `"A Newspaper That Knows\nOnly You Will Ever Read It"` |
| `deck`          | string        | **yes**  | `"Personalised journalism leaves the laboratory..."` |
| `byline`        | string        | **yes**  | `"By the OpenPaper Desk · Filed 06:14 in Oslo"` |
| `paragraphs`    | array[string] | **yes**  | `["The spread you are reading...", ...]` |
| `annotation`    | string        | **yes**  | `"because you follow\nPublic Technology"` |
| `photo_caption` | string        | **yes**  | `"First light over the harbour..."` |
| `url`           | string        | no       | Link to original article (clickable headline) |
| `image_url`     | string        | no       | Article image URL (renders inside frame; falls back to SVG placeholder) |

### Title line-splitting

Use `\n` in the title string to split across multiple lines. The template wraps each segment in an `<span class="ink-line">` with staggered animation delays. Single-line titles work fine too.

### Annotation

The annotation is rendered as a handwritten margin note in the lead photo area. It explains **why** this story was chosen (e.g., "because you follow Public Technology"). Use `\n` for line breaks.

---

## `stories[]`

| Field       | Type          | Required | Example |
|-------------|---------------|----------|---------|
| `kicker`    | string        | **yes**  | `"Climate"` |
| `title`     | string        | **yes**  | `"Fjord Hits a Record..."` |
| `paragraphs`| array[string] | **yes**  | `["Marine stations...", ...]` |
| `size`      | string        | **yes**  | See size table below |
| `section`   | string        | **yes**  | See section table below |
| `has_thumb`  | bool         | no       | `true` (broadsheet only -- shows thumbnail placeholder) |
| `url`       | string        | no       | Link to original article |
| `image_url` | string        | no       | Article image URL |

### Sizes

| Size   | CSS class | Font-size |
|--------|-----------|-----------|
| `sm`   | `.h-sm`   | 14px      |
| `md`   | `.h-md`   | 17px      |
| `lg`   | `.h-lg`   | 22px      |

### Sections

6-column grid. Column 6 is the right rail (weather/markets/index), not for stories.

| Section | Position                |
|---------|-------------------------|
| `col1`  | Column 1 (below briefs) |
| `col2`  | Column 2                |
| `col3`  | Column 3                |
| `col4`  | Column 4                |
| `col5`  | Column 5                |

---

## `briefs[]`

| Field  | Type   | Required | Example |
|--------|--------|----------|---------|
| `bold` | string | **yes**  | `"Oslo"` |
| `text` | string | **yes**  | `"moves to publish the source of every algorithm it runs."` |
| `url`  | string | no       | Link to original article |

Briefs render as a bulleted list at the top of column 1 in both templates. Each brief is one line: **bold** followed by text.

---

## `sections_index[]`

| Field  | Type   | Required | Example        |
|--------|--------|----------|----------------|
| `name` | string | **yes**  | `"Public Tech"` |
| `page` | string | **yes**  | `"A2"`          |

The "Inside Today" box. Rendered in a box in column 6.

---

## `word_of_day`

| Field        | Type   | Required | Example |
|--------------|--------|----------|---------|
| `word`       | string | **yes**  | `"Petrichor"` |
| `definition` | string | **yes**  | `"the scent of first rain"` |

Rendered in the footer bar of both templates.

---

## Slot budget

### Slot budget (14 articles typical)

| Slot             | Count  | Populated by            |
|------------------|--------|-------------------------|
| Lead             | 1      | `lead` object           |
| Stories (col1-5) | ~8-10  | `stories[]` array       |
| Briefs           | ~5-7   | `briefs[]` array        |
| Weather          | 1 box  | `weather` object (col6) |
| Markets          | 1 box  | `markets[]` array (col6)|
| Inside Today     | 1 box  | `sections_index[]` (col6)|
| Word of Day      | 1      | `word_of_day` (footer)  |

Story distribution across columns:

| Column | Typical content             | Recommended stories |
|--------|-----------------------------|---------------------|
| col1   | Briefs list + 1-2 stories   | 1-2                 |
| col2   | 2-3 stories                 | 2-3                 |
| col3   | 2-3 stories                 | 2-3                 |
| col4   | 2-3 stories                 | 2-3                 |
| col5   | 2-3 stories                 | 2-3                 |
| col6   | Weather + Markets + Index   | 0 (rail only)       |

## Complete broadsheet example

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
  - {name: OSEBX, value: "1,486", change: "+0.6%", direction: up}
  - {name: "USD / NOK", value: "10.42", change: "−0.3%", direction: down}
  - {name: Brent, value: "$77.10", change: "+1.1%", direction: up}

lead:
  kicker: "The Lead · Public Technology"
  title: "A Newspaper That Knows\nOnly You Will Ever Read It"
  deck: "Personalised journalism leaves the laboratory and lands on the breakfast table."
  byline: "By the OpenPaper Desk · Filed 06:14 in Oslo"
  paragraphs:
    - "The spread you are reading was assembled in the seconds after you opened it."
    - "Proponents argue that a paper which understands its reader can cut through the noise."
    - "Critics counter that a public square requires a shared front page."
    - "For now the experiment is small and deliberately legible."
  annotation: "because you follow\nPublic Technology"
  photo_caption: "First light over the harbour, captured at 04:51 this morning."

stories:
  - kicker: Climate
    title: "Fjord Hits a Record as Summer Arrives Three Weeks Early"
    paragraphs:
      - "Marine stations along the coast reported the warmest spring readings in the instrument era."
      - "Researchers caution that a single warm spring is weather, not climate."
    size: lg
    has_thumb: true
    section: col2

  - kicker: Science
    title: "The Aurora Returns Early This Year"
    paragraphs:
      - "Heightened solar activity may push the northern lights south of their usual latitudes."
    size: sm
    section: col2

  - kicker: "City Hall"
    title: "A Budget Written in Public, Line by Line"
    paragraphs:
      - "Every line of the coming municipal budget will be drafted on an open ledger."
      - "Officials describe the experiment as radical legibility."
    size: lg
    section: col3

  - kicker: Transit
    title: "The Metro Learns to Wait"
    paragraphs:
      - "New signalling holds a departing train sixty seconds when a connection runs late."
    size: sm
    section: col3

  - kicker: Housing
    title: "Co-ops Vote to Share the Roof"
    paragraphs:
      - "A cluster of housing co-operatives will pool their rooftops for solar and a common garden."
    size: sm
    section: col3

  - kicker: Culture
    title: "The Library That Lends Only Silence"
    paragraphs:
      - "A new reading room near Bjørvika offers nothing to read — only a chair and a window."
    size: lg
    has_thumb: true
    section: col4

  - kicker: Books
    title: "The Slow Novel Finds Its Readers"
    paragraphs:
      - "A 900-page debut, written over a decade, is the season's unlikely success."
    size: sm
    section: col4

  - kicker: "Sport · Eliteserien"
    title: "A Late Goal, and a City Exhales"
    paragraphs:
      - "Stoppage time delivered the result the table demanded."
    size: lg
    section: col5

  - kicker: "Opinion · The Last Word"
    title: "In Praise of Being Hard to Reach"
    paragraphs:
      - "Our columnist makes the case for the unanswered message."
    size: sm
    section: col5

  - kicker: Profile
    title: "The Cartographer of Small Streets"
    paragraphs:
      - "One man has spent twelve years mapping the city's shortcuts and hidden courtyards."
    size: sm
    section: col5

  - kicker: Health
    title: "Clinics Trial the Unhurried Appointment"
    paragraphs:
      - "A pilot lengthens the standard visit to thirty minutes."
    size: md
    section: col1

briefs:
  - {bold: Oslo, text: "moves to publish the source of every algorithm it runs."}
  - {bold: Krone, text: "steadies after a volatile week as energy futures cool."}
  - {bold: Council, text: "weighs a four-day civic week for the digital agency."}
  - {bold: Metro, text: "trials a sixty-second hold for late connections."}
  - {bold: Harbour, text: "bathing season opens early as fjord temperatures climb."}

sections_index:
  - {name: Public Tech, page: A2}
  - {name: "Science & Climate", page: A6}
  - {name: Markets, page: B1}
  - {name: Culture, page: C3}
  - {name: Sport, page: D1}

word_of_day:
  word: Petrichor
  definition: "the scent of first rain"
```

## Validation checklist

Use this when reviewing an edition YAML before rendering:

- [ ] `template` is `"broadsheet"`
- [ ] `edition_name`, `date`, `volume`, `number`, `location`, `reading_time`, `tagline`, `printed_time` are present (`volume` and `number` can be `"auto"`)
- [ ] `weather` has `icon`, `temp`, `description`, `high`, `low`, `wind`, and `forecast[]`
- [ ] `weather.icon` is one of: `cloud`, `sun`, `rain`, `snow`
- [ ] `lead` has `kicker`, `title`, `deck`, `byline`, `paragraphs`, `annotation`, `photo_caption`
- [ ] All `stories[]` have `kicker`, `title`, `paragraphs`, `size`, `section`
- [ ] Story sizes are `sm`, `md`, or `lg`
- [ ] Story sections use string values (`"col1"` not `1`)
- [ ] Story sections are `col1` through `col5` (not `col6`)
- [ ] All `briefs[]` have `bold` and `text`
- [ ] `sections_index[]` items have `name` and `page`
- [ ] `word_of_day` has `word` and `definition`

---

## Differences from curation-guide.md

The edition schema in `curation-guide.md` was written before the templates were finalized.
Key divergences that this document corrects:

| curation-guide.md says          | Templates actually use           |
|---------------------------------|----------------------------------|
| `stories[].column: 1` (int)    | `stories[].section: "col1"` (string) |
| `lead.body` (single string)    | `lead.paragraphs` (array of strings) |
| `lead.article_ref`             | Not required (inline content is the norm) |
| `lead.photo_alt`               | `lead.photo_caption`             |
| `stories[].body` (string)      | `stories[].paragraphs` (array)   |
| `stories[].annotation`         | Not rendered (only the lead gets an annotation) |
| `masthead.title`, `masthead.tagline` | Top-level `tagline`; masthead is hardcoded as "OpenPaper" |
| `edition_number`               | Separate `volume` + `number` fields |
| `weather.current.temp_c`       | `weather.temp` (flat structure)  |
| `weather.forecast[].high_c`, `low_c` | `weather.forecast[].temp` (single value) |
| Sizes: only sm/md/lg           | Confirmed: only sm/md/lg |
| `briefs[].title`, `source`     | `briefs[].bold`, `text`          |
