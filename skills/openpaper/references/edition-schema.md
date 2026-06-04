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
| `template`       | string | **yes**         | `"broadsheet"` or `"folio"`                    | Selects the Jinja2 template |
| `edition_name`   | string | **yes**         | `"morning"`                                    | Used in output filename |
| `date`           | string | **yes**         | `"Thursday, June 4, 2026"`                     | Human-readable, appears in dateline |
| `date_formal`    | string | folio: **yes**, broadsheet: optional | `"Thursday, the Fourth of June, MMXXVI"` | Folio dateline uses this instead of `date` |
| `volume`         | string | **yes**         | `"MMXXVI"` or `"auto"`                         | Roman numeral year; `"auto"` uses current year |
| `number`         | string | **yes**         | `"156"` or `"auto"`                            | Issue number; `"auto"` increments from previous editions |
| `location`       | string | **yes**         | `"Oslo, Norway"`                               | Folio splits on comma and uses first part |
| `reading_time`   | string | broadsheet: **yes**, folio: optional | `"22 min"`                  | Broadsheet dateline displays this |
| `article_count`  | int    | **yes**         | `14`                                           | Shown in folio bar |
| `tagline`        | string | **yes**         | `"All the news that fits the day you are about to have."` | Broadsheet: left flank. Folio: footer |
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

Broadsheet renders the full weather box in column 6 (the right rail).
Folio renders a compact weather box at the bottom of column 1.

---

## `markets[]`

| Field       | Type   | Required | Example         |
|-------------|--------|----------|-----------------|
| `name`      | string | **yes**  | `"OSEBX"`       |
| `value`     | string | **yes**  | `"1,486"`       |
| `change`    | string | **yes**  | `"+0.6%"`       |
| `direction` | string | **yes**  | `"up"` or `"down"` |

Broadsheet: rendered in a box in column 6.
Folio: rendered in a box in column 6.

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

### Sizes by template

| Size   | Broadsheet | Folio | CSS class | Broadsheet font-size | Folio font-size |
|--------|:----------:|:-----:|-----------|----------------------|-----------------|
| `sm`   | yes        | yes   | `.h-sm`   | 14px                 | 13.5px          |
| `md`   | yes        | yes   | `.h-md`   | 17px                 | 16px            |
| `lg`   | yes        | yes   | `.h-lg`   | 22px                 | 21px            |
| `xl`   | no         | yes   | `.h-xl`   | --                   | 30px            |
| `mega` | no         | yes   | `.h-mega` | --                   | 52px            |

Broadsheet only uses `sm`, `md`, `lg`. Using `xl` or `mega` in a broadsheet story will produce an undefined CSS class -- avoid it.

### Sections by template

**Broadsheet** -- 6-column grid. Column 6 is the right rail (weather/markets/index), not for stories.

| Section | Position                |
|---------|-------------------------|
| `col1`  | Column 1 (below briefs) |
| `col2`  | Column 2                |
| `col3`  | Column 3                |
| `col4`  | Column 4                |
| `col5`  | Column 5                |

**Folio** -- 6-column grid. Column 3 is the lead (rendered separately), not for stories.

| Section | Position                          |
|---------|-----------------------------------|
| `col1`  | Column 1 (below briefs + weather) |
| `col2`  | Column 2                          |
| `col4`  | Column 4                          |
| `col5`  | Column 5                          |
| `col6`  | Column 6 (above markets/index)    |

Note: folio column 3 (`lead`) is reserved for the lead story and is never assigned via `stories[].section`.

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

The "Inside Today" box. Broadsheet: rendered in a box in column 6. Folio: rendered in a box in column 6.

---

## `word_of_day`

| Field        | Type   | Required | Example |
|--------------|--------|----------|---------|
| `word`       | string | **yes**  | `"Petrichor"` |
| `definition` | string | **yes**  | `"the scent of first rain"` |

Rendered in the footer bar of both templates.

---

## Folio-only fields

The following fields are only used by `folio.html.j2`. Broadsheet ignores them.

### `opinion`

| Field               | Type                       | Required (folio) | Example |
|---------------------|----------------------------|------------------|---------|
| `editor_title`      | string                     | **yes**          | `"On Writing for a Readership of One"` |
| `editor_paragraphs` | array[string]              | **yes**          | `["When more than a third...", ...]` |
| `essay_title`       | string                     | **yes**          | `"When the Front Page Becomes a Mirror..."` |
| `essay_columns`     | array[array[string]]       | **yes**          | Two arrays of paragraph strings (left and right column) |
| `letters`           | array[letter]              | **yes**          | See below |

#### `opinion.essay_columns`

Exactly two arrays. The first array is the left column's paragraphs, the second is the right column's paragraphs. The template renders them side by side in a `.lv2` grid.

```yaml
essay_columns:
  - - "First paragraph of left column..."
    - "Second paragraph of left column..."
  - - "First paragraph of right column..."
    - "Second paragraph of right column..."
```

#### `opinion.letters[]`

| Field         | Type   | Required | Example |
|---------------|--------|----------|---------|
| `title`       | string | **yes**  | `"\"I Miss Disagreeing\""` |
| `text`        | string | **yes**  | `"A fair question. The short answer..."` |
| `attribution` | string | **yes**  | `"K.S., Grünerløkka"` |

### `below_fold[]`

**EXACTLY 6 items.** The folio template renders these in a 6-column grid (`grid-template-columns: repeat(6,1fr)`). Fewer than 6 leaves empty columns; more than 6 overflows.

| Field    | Type   | Required | Example |
|----------|--------|----------|---------|
| `kicker` | string | **yes**  | `"World"` |
| `title`  | string | **yes**  | `"A Quieter Summit..."` |
| `text`   | string | **yes**  | `"Negotiators departed..."` |
| `url`    | string | no       | Link to original article |

---

## Slot budget

### Broadsheet (14 articles typical)

| Slot             | Count  | Populated by            |
|------------------|--------|-------------------------|
| Lead             | 1      | `lead` object           |
| Stories (col1-5) | ~8-10  | `stories[]` array       |
| Briefs           | ~5-7   | `briefs[]` array        |
| Weather          | 1 box  | `weather` object (col6) |
| Markets          | 1 box  | `markets[]` array (col6)|
| Inside Today     | 1 box  | `sections_index[]` (col6)|
| Word of Day      | 1      | `word_of_day` (footer)  |

Story distribution across broadsheet columns:

| Column | Typical content             | Recommended stories |
|--------|-----------------------------|---------------------|
| col1   | Briefs list + 1-2 stories   | 1-2                 |
| col2   | 2-3 stories                 | 2-3                 |
| col3   | 2-3 stories                 | 2-3                 |
| col4   | 2-3 stories                 | 2-3                 |
| col5   | 2-3 stories                 | 2-3                 |
| col6   | Weather + Markets + Index   | 0 (rail only)       |

### Folio (18 articles typical)

| Slot             | Count  | Populated by              |
|------------------|--------|---------------------------|
| Lead             | 1      | `lead` object (col3)      |
| Stories (col1,2,4,5,6) | ~7-10 | `stories[]` array   |
| Briefs           | ~5-7   | `briefs[]` array          |
| Opinion band     | 1      | `opinion` object          |
| Below fold       | **6**  | `below_fold[]` array      |
| Weather          | 1 box  | `weather` object (col1)   |
| Markets          | 1 box  | `markets[]` array (col6)  |
| Inside Today     | 1 box  | `sections_index[]` (col6) |
| Word of Day      | 1      | `word_of_day` (footer)    |

Story distribution across folio columns:

| Column | Typical content                     | Recommended stories |
|--------|-------------------------------------|---------------------|
| col1   | Briefs + weather box + 0-1 stories  | 0-1                 |
| col2   | 2-3 stories                         | 2-3                 |
| col3   | Lead (auto-filled, not in stories)  | --                  |
| col4   | 2-3 stories                         | 2-3                 |
| col5   | 2-3 stories                         | 2-3                 |
| col6   | 1-2 stories + markets + index       | 1-2                 |

---

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

---

## Complete folio example

```yaml
template: folio
edition_name: morning
date: "Wednesday, June 4, 2026"
date_formal: "Wednesday, the Fourth of June, MMXXVI"
volume: auto
number: auto
location: "Oslo, Norway"
reading_time: "24 min"
article_count: 18
tagline: "All the news that fits the day you are about to have."
printed_time: "06:22 CET"

weather:
  icon: rain
  temp: 15
  description: "Morning showers, clearing by afternoon"
  high: 20
  low: 13
  wind: "ESE 10 km/h"
  forecast:
    - {day: THU, temp: 18}
    - {day: FRI, temp: 20}
    - {day: SAT, temp: 19}
    - {day: SUN, temp: 17}

markets:
  - {name: OSEBX, value: "2,044", change: "−0.7%", direction: down}
  - {name: "USD / NOK", value: "9.32", change: "−0.1%", direction: down}
  - {name: "EUR / NOK", value: "10.80", change: "−0.2%", direction: down}

lead:
  kicker: "The Lead · Artificial Intelligence"
  title: "They're Made\nOut of Weights"
  deck: "A short fiction reimagines the classic for the age of large language models."
  byline: "By Max Leiter · Via Hacker News · Filed 06:22 in Oslo"
  paragraphs:
    - "\"They're made out of weights.\" So begins Max Leiter's riff on Terry Bisson's 1991 story."
    - "The original story's aliens were horrified that humans could think. Leiter's version inverts the horror."
    - "The piece struck a nerve on Hacker News, climbing to 759 points."
    - "What makes Leiter's homage linger is its refusal to resolve the question."
  annotation: "because you follow\nTechnology & AI"
  photo_caption: "Eighty layers of floating-point arithmetic."

stories:
  - kicker: "Artificial Intelligence"
    title: "Google Releases Gemma 4, an Encoder-Free Multimodal Model"
    paragraphs:
      - "Google DeepMind released Gemma 4 12B this week."
      - "The release drew 855 points on Hacker News."
      - "For developers, the appeal is practical: a capable multimodal model that runs locally."
    size: lg
    section: col2

  - kicker: "AI & Education"
    title: "Failing Grades Soar as AI Usage Spreads Through Berkeley CS"
    paragraphs:
      - "35% of CS 10 students received F grades."
      - "Faculty point to widespread AI tool usage as a contributing factor."
    size: md
    section: col2

  - kicker: "Industry · AI Economics"
    title: "Uber Caps AI Coding Tools at $1,500 per Engineer per Month"
    paragraphs:
      - "Uber blew through its 2026 AI budget in four months."
      - "The cap emerged after agentic coding tools proved far more token-hungry."
      - "The story drew 501 points and 620 comments."
    size: lg
    section: col4

  - kicker: "Philosophy · AI"
    title: "Ted Chiang: Artificial Intelligence Is Not Conscious"
    paragraphs:
      - "In a new essay for The Atlantic, Chiang argues that AI companies have encouraged anthropomorphism."
      - "Chiang takes particular aim at Anthropic's 84-page constitution for Claude."
    size: md
    section: col4

  - kicker: "Programming Languages"
    title: "Elixir v1.20 Arrives with Gradual Typing"
    paragraphs:
      - "José Valim released Elixir v1.20, marking a major milestone."
      - "The new release performs type inference across every expression."
      - "With 792 points, it was the second-most upvoted story."
    size: lg
    section: col5

  - kicker: "Security · Cryptography"
    title: "Let's Encrypt Charts a Post-Quantum Path"
    paragraphs:
      - "Let's Encrypt is backing Merkle Tree Certificates."
      - "Post-quantum algorithms produce much larger signatures."
    size: md
    section: col5

  - kicker: "Security · AI"
    title: "Can LLMs Hack a Deliberately Vulnerable App?"
    paragraphs:
      - "A researcher spent $1,500 in API credits on the experiment."
      - "Models could identify surface-level issues but struggled with exploit chains."
    size: md
    section: col6

briefs:
  - {bold: "Espressif", text: "announces the ESP32-S31 for IoT applications."}
  - {bold: "DaVinci Resolve 21", text: "ships with a new Photo page and AI-powered media search."}
  - {bold: "Zig", text: "gains Gooey, a GPU-accelerated UI framework."}
  - {bold: "Anthropic", text: "publishes a post on how it contains Claude across products."}
  - {bold: "Mathematicians", text: "issue a formal warning as AI gains ground on proof verification."}
  - {bold: "Massachusetts", text: "witnesses a meteor explosion over the state."}
  - {bold: "SQL", text: "gets a love letter arguing it remains the most durable developer skill."}

sections_index:
  - {name: "AI & Models", page: A1}
  - {name: "Industry", page: A2}
  - {name: "Languages", page: A3}
  - {name: "Security", page: A4}
  - {name: "Hardware", page: A5}
  - {name: "Opinion", page: B1}

opinion:
  editor_title: "On Printing a Newspaper Where Every Headline Contains A and I"
  editor_paragraphs:
    - "When more than a third of today's articles concern AI, the editor must pause."
    - "The honest answer is: both. The front page is genuinely dominated by AI stories."
    - "A human editor would face the same raw material and make similar choices."

  essay_title: "When the Machine Reads the News\nfor an Audience of One"
  essay_columns:
    - - "There is something quietly radical about a newspaper for one reader."
      - "Traditional newspapers solve a different problem: they must serve a broad audience."
      - "A newspaper for one can lead with a short fiction about floating-point weights."
    - - "But freedom from consensus carries its own risk."
      - "The antidote is intentional serendipity."
      - "The question this format asks is not 'what do you want to read?' but 'what do you want to want to read?'"

  letters:
    - title: "\"How Do You Know What I'll Find Interesting?\""
      text: "The short answer: I don't, not yet. Today's edition is a first draft."
      attribution: "The Editor, in anticipation"
    - title: "\"Is This Just a Filter Bubble?\""
      text: "It could be. The 20% discovery rule is a structural defence."
      attribution: "The Desk, defensively"
    - title: "\"I Notice You Chose a Story About Yourself\""
      text: "Not quite — the lead is about weights, not about any particular model."
      attribution: "The Editor, chastened"

below_fold:
  - kicker: "Retrocomputing"
    title: "A Deep Dive into the PlayStation's Architecture"
    text: "Rodrigo Copetti's analysis examines the R3000 CPU and rendering pipeline."
  - kicker: "Health"
    title: "A Personal Account of Anti-NMDA Receptor Encephalitis"
    text: "Andrew Gallant shares his diagnosis with a rare autoimmune disorder."
  - kicker: "Hardware Hacking"
    title: "Patching a Guitar Amplifier's Firmware via UART"
    text: "A reverse engineer discovers debug headers in a Yamaha service manual."
  - kicker: "Infrastructure"
    title: "Thunderbolt InfiniBand at Home"
    text: "A networking experiment pushes Thunderbolt to its theoretical limits."
  - kicker: "History"
    title: "Under Notre-Dame, 1,700 Years of History"
    text: "Excavations beneath the cathedral reveal layer upon layer of Parisian life."
  - kicker: "Culture"
    title: "The US Army Corps Built a Scale Model of the Bay"
    text: "A two-acre hydraulic model of San Francisco Bay, built in 1957, still stands."

word_of_day:
  word: "Stochastic"
  definition: "involving random probability — as in the parrots, or perhaps not"
```

---

## Validation checklist

Use this when reviewing an edition YAML before rendering:

- [ ] `template` is `"broadsheet"` or `"folio"`
- [ ] `edition_name`, `date`, `volume`, `number`, `location`, `tagline`, `printed_time` are present (`volume` and `number` can be `"auto"`)
- [ ] If folio: `date_formal` is present
- [ ] If broadsheet: `reading_time` is present
- [ ] `weather` has `icon`, `temp`, `description`, `high`, `low`, `wind`, and `forecast[]`
- [ ] `weather.icon` is one of: `cloud`, `sun`, `rain`, `snow`
- [ ] `lead` has `kicker`, `title`, `deck`, `byline`, `paragraphs`, `annotation`, `photo_caption`
- [ ] All `stories[]` have `kicker`, `title`, `paragraphs`, `size`, `section`
- [ ] Story sizes are valid for the template (broadsheet: sm/md/lg; folio: sm/md/lg/xl/mega)
- [ ] Story sections use string values (`"col1"` not `1`)
- [ ] Broadsheet story sections are `col1` through `col5` (not `col6`)
- [ ] Folio story sections are `col1`, `col2`, `col4`, `col5`, `col6` (not `col3`)
- [ ] All `briefs[]` have `bold` and `text`
- [ ] `sections_index[]` items have `name` and `page`
- [ ] `word_of_day` has `word` and `definition`
- [ ] If folio: `opinion` has `editor_title`, `editor_paragraphs`, `essay_title`, `essay_columns`, `letters`
- [ ] If folio: `opinion.essay_columns` has exactly 2 arrays
- [ ] If folio: `opinion.letters[]` items have `title`, `text`, `attribution`
- [ ] If folio: `below_fold` has **exactly 6 items**
- [ ] If folio: `below_fold[]` items have `kicker`, `title`, `text`

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
| Sizes: only sm/md/lg           | Folio also supports `xl` and `mega` |
| `briefs[].title`, `source`     | `briefs[].bold`, `text`          |
