# /// script
# requires-python = ">=3.11"
# dependencies = ["jinja2", "pyyaml"]
# ///
"""OpenPaper render — generate an HTML newspaper edition from curated articles.

Usage:
    uv run render.py --data-dir .openpaper --edition edition.yaml
    uv run render.py --data-dir .openpaper --edition edition.yaml --output custom.html
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Fixed UI labels rendered by the template (section headings, footer, etc.).
# English is the default; a locale bundle or per-edition `ui:` block overrides it.
DEFAULT_LABELS = {
    "folio_tagline": "Curated for One Reader",
    "articles": "Articles",
    "masthead_note": "A daily edition, composed this morning, for you and no one else.",
    "caption_above": "Above",
    "briefs": "The Briefs",
    "more": "More This Morning",
    "weather": "The Weather",
    "hi": "Hi",
    "lo": "Lo",
    "wind_label": "Wind",
    "markets": "Markets at Dawn",
    "inside": "Inside Today",
    "morning_edition": "The Morning Edition",
    "word_of_day": "Word of the Day",
    "printed": "Printed Fresh",
}

# Bundled translations of DEFAULT_LABELS, selected via the edition's `locale` field.
LOCALE_LABELS = {
    "nb": {
        "folio_tagline": "Kuratert for én leser",
        "articles": "artikler",
        "masthead_note": "En daglig utgave, satt sammen i morges, for deg og ingen andre.",
        "caption_above": "Over",
        "briefs": "Kort sagt",
        "more": "Mer i morges",
        "weather": "Været",
        "hi": "Opp",
        "lo": "Ned",
        "wind_label": "Vind",
        "markets": "Børs ved daggry",
        "inside": "I avisen i dag",
        "morning_edition": "Morgenutgaven",
        "word_of_day": "Dagens ord",
        "printed": "Trykt friskt",
    },
}

ROMAN_NUMERALS = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def to_roman(n: int) -> str:
    result = []
    for value, numeral in ROMAN_NUMERALS:
        while n >= value:
            result.append(numeral)
            n -= value
    return "".join(result)


def resolve_edition_number(edition: dict, data_dir: Path) -> None:
    """Auto-assign volume and number if missing or set to 'auto'.

    Scans previous rendered editions in data_dir/editions/ to find the
    highest issue number, then increments for a new day or adds a letter
    suffix (b, c, ...) for same-day editions.
    """
    needs_volume = not edition.get("volume") or edition["volume"] == "auto"
    needs_number = not edition.get("number") or edition["number"] == "auto"

    if not needs_volume and not needs_number:
        return

    if needs_volume:
        edition["volume"] = to_roman(datetime.now().year)

    if not needs_number:
        return

    editions_dir = data_dir / "editions"
    today = datetime.now().strftime("%Y-%m-%d")
    edition_name = edition.get("edition_name", "")

    highest_number = 0
    today_numbers = []

    for html_file in sorted(editions_dir.glob("*.html")):
        try:
            text = html_file.read_text(encoding="utf-8")
        except OSError:
            continue

        match = re.search(r"No\.\s*(\d+)([a-z]?)", text)
        if not match:
            continue

        num = int(match.group(1))
        suffix = match.group(2)
        highest_number = max(highest_number, num)

        if html_file.name.startswith(today):
            today_numbers.append((num, suffix))

    if not today_numbers:
        edition["number"] = str(highest_number + 1)
    else:
        day_num = today_numbers[0][0]
        existing_suffixes = {s for _, s in today_numbers}
        if "" not in existing_suffixes:
            edition["number"] = str(day_num)
        else:
            for letter in "bcdefgh":
                if letter not in existing_suffixes:
                    edition["number"] = f"{day_num}{letter}"
                    break

    sys.stderr.write(
        f"Auto-assigned: Vol. {edition['volume']} No. {edition['number']}\n"
    )


def resolve_labels(edition: dict) -> None:
    """Populate edition['ui'] with locale-aware UI label defaults.

    Precedence, lowest to highest: English DEFAULT_LABELS, the selected locale's
    bundle (from edition['locale'], default 'en'), then any per-edition 'ui'
    overrides already present in the YAML. The template reads edition.ui.<key>
    directly, so this guarantees every label is defined.
    """
    locale = edition.get("locale", "en")
    edition["ui"] = {
        **DEFAULT_LABELS,
        **LOCALE_LABELS.get(locale, {}),
        **(edition.get("ui") or {}),
    }


def load_edition(edition_path: Path, data_dir: Path) -> dict:
    """Load the edition YAML and resolve article references to full content."""
    with open(edition_path) as f:
        edition = yaml.safe_load(f)

    resolve_edition_number(edition, data_dir)
    resolve_labels(edition)

    incoming_dir = data_dir / "incoming"

    if "lead" in edition and "article_ref" in edition["lead"]:
        edition["lead"] = resolve_article(
            edition["lead"], incoming_dir, is_lead=True
        )

    if "stories" in edition:
        edition["stories"] = [
            resolve_article(s, incoming_dir) for s in edition["stories"]
        ]

    if "briefs" in edition:
        edition["briefs"] = [
            resolve_brief(b, incoming_dir) for b in edition["briefs"]
        ]

    if "below_fold" in edition:
        edition["below_fold"] = [
            resolve_article(s, incoming_dir) for s in edition["below_fold"]
        ]

    return edition


def resolve_article(ref: dict, incoming_dir: Path, is_lead: bool = False) -> dict:
    """Resolve an article reference to full content.

    If the ref already has inline content (title, paragraphs), return as-is.
    Otherwise look up article_ref in the incoming directory.
    """
    if "paragraphs" in ref and "title" in ref:
        return ref

    article_ref = ref.get("article_ref")
    if not article_ref:
        return ref

    article = find_article(article_ref, incoming_dir)
    if not article:
        sys.stderr.write(f"Warning: could not resolve article_ref: {article_ref}\n")
        return ref

    merged = {**ref}
    if "title" not in merged:
        merged["title"] = article.get("title", "Untitled")
    if "paragraphs" not in merged:
        content = article.get("content") or article.get("summary") or ""
        merged["paragraphs"] = split_paragraphs(content)
    if "kicker" not in merged and not is_lead:
        merged["kicker"] = article.get("source", "")
    if "url" not in merged:
        merged["url"] = article.get("url", "")
    if "image_url" not in merged:
        merged["image_url"] = article.get("image_url")
    if is_lead:
        if "deck" not in merged:
            merged["deck"] = article.get("summary", "")
        if "byline" not in merged:
            author = article.get("author", "the OpenPaper Desk")
            merged["byline"] = f"By {author}"

    return merged


def resolve_brief(ref: dict, incoming_dir: Path) -> dict:
    """Resolve a brief reference."""
    if "bold" in ref and "text" in ref:
        return ref

    article_ref = ref.get("article_ref")
    if not article_ref:
        return ref

    article = find_article(article_ref, incoming_dir)
    if not article:
        return ref

    title = article.get("title", "")
    source = article.get("source", "")
    summary = article.get("summary") or article.get("content") or ""
    first_sentence = summary.split(". ")[0] + "." if summary else title

    return {
        "bold": ref.get("bold", source.capitalize()),
        "text": ref.get("text", first_sentence),
        "url": ref.get("url", article.get("url", "")),
    }


def find_article(ref: str, incoming_dir: Path) -> dict | None:
    """Find an article by URL or filename in the incoming directory."""
    if not incoming_dir.exists():
        return None

    for path in incoming_dir.glob("*.json"):
        try:
            with open(path) as f:
                article = json.load(f)
            if article.get("url") == ref:
                return article
        except (json.JSONDecodeError, KeyError):
            continue

    slug = slugify(ref)
    candidate = incoming_dir / f"{slug}.json"
    if candidate.exists():
        try:
            with open(candidate) as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass

    return None


def split_paragraphs(text: str) -> list[str]:
    """Split content text into paragraphs."""
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]
    return paragraphs


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    import re

    text = text.lower().strip()
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")


def build_weather_svg(icon: str) -> str:
    """Return an inline SVG for the weather icon."""
    icons = {
        "cloud": (
            '<svg width="38" height="38" viewBox="0 0 44 44" fill="none" '
            'stroke="var(--ink)" stroke-width="1.6">'
            '<g class="wx-cloud"><path d="M12 30h20a6 6 0 0 0 0-12 '
            '8 8 0 0 0-15-2 6 6 0 0 0-5 14z" fill="rgba(28,24,19,0.08)"/>'
            "</g></svg>"
        ),
        "sun": (
            '<svg width="38" height="38" viewBox="0 0 44 44" fill="none" '
            'stroke="var(--ink)" stroke-width="1.6">'
            '<g class="wx-sun"><circle cx="22" cy="22" r="7"/>'
            '<line x1="22" y1="4" x2="22" y2="10"/>'
            '<line x1="22" y1="34" x2="22" y2="40"/>'
            '<line x1="4" y1="22" x2="10" y2="22"/>'
            '<line x1="34" y1="22" x2="40" y2="22"/>'
            "</g></svg>"
        ),
        "rain": (
            '<svg width="38" height="38" viewBox="0 0 44 44" fill="none" '
            'stroke="var(--ink)" stroke-width="1.6">'
            '<path d="M12 26h20a6 6 0 0 0 0-12 8 8 0 0 0-15-2 '
            '6 6 0 0 0-5 14z" fill="rgba(28,24,19,0.08)"/>'
            '<g class="wx-rain">'
            '<line x1="16" y1="30" x2="14" y2="37"/>'
            '<line x1="22" y1="30" x2="20" y2="37"/>'
            '<line x1="28" y1="30" x2="26" y2="37"/>'
            "</g></svg>"
        ),
        "snow": (
            '<svg width="38" height="38" viewBox="0 0 44 44" fill="none" '
            'stroke="var(--ink)" stroke-width="1.6">'
            '<path d="M12 24h20a6 6 0 0 0 0-12 8 8 0 0 0-15-2 '
            '6 6 0 0 0-5 14z" fill="rgba(28,24,19,0.08)"/>'
            '<circle cx="16" cy="33" r="1.5" fill="var(--ink)"/>'
            '<circle cx="22" cy="36" r="1.5" fill="var(--ink)"/>'
            '<circle cx="28" cy="32" r="1.5" fill="var(--ink)"/>'
            "</svg>"
        ),
    }
    return icons.get(icon, icons["cloud"])


def render_edition(edition: dict, templates_dir: Path) -> str:
    """Render the edition to HTML using the appropriate Jinja2 template."""
    template_name = edition.get("template", "broadsheet")
    template_file = f"{template_name}.html.j2"

    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["weather_svg"] = build_weather_svg

    template = env.get_template(template_file)
    return template.render(edition=edition)


def main():
    parser = argparse.ArgumentParser(
        description="Render an OpenPaper newspaper edition"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".openpaper"),
        help="Path to .openpaper/ directory",
    )
    parser.add_argument(
        "--edition",
        type=Path,
        required=True,
        help="Path to edition YAML file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output HTML path (default: .openpaper/editions/<date>.html)",
    )
    parser.add_argument(
        "--templates-dir",
        type=Path,
        default=TEMPLATES_DIR,
        help="Path to Jinja2 templates directory",
    )
    args = parser.parse_args()

    if not args.edition.exists():
        sys.stderr.write(f"Error: edition file not found: {args.edition}\n")
        sys.exit(1)

    edition = load_edition(args.edition, args.data_dir)

    html = render_edition(edition, args.templates_dir)

    if args.output:
        output_path = args.output
    else:
        editions_dir = args.data_dir / "editions"
        editions_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        template_name = edition.get("template", "broadsheet")
        edition_name = edition.get("edition_name", "morning")
        output_path = editions_dir / f"{date_str}-{edition_name}-{template_name}.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    sys.stderr.write(f"Edition rendered: {output_path}\n")
    print(str(output_path))


if __name__ == "__main__":
    main()
