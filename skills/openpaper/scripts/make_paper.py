# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""OpenPaper agent-free pipeline — fetch -> curate -> render, no Claude.

This is the entry point for `engine: local`. It chains the existing fetch and
render scripts around the local curation engine (curate.py), so a daily paper
can be produced from a plain shell with a local model and no Claude Code session.

    uv run make_paper.py --data-dir .openpaper

By default it ends by launching the preview server (serve.py) and opening the
edition in a browser — the same UX as the Claude flow. Pass --no-serve for
headless/cron runs that should just render and exit.

On a fresh clone it self-bootstraps: it creates the `.openpaper/` scaffolding
(config.yaml with engine: local, a starter preferences.md, and a couple of
default news fetchers) so it runs with no prior Claude session. Run the
/openpaper skill once to tailor sources and preferences to you.

If a `config.yaml` already exists with `engine` != `local`, it points you back
to the Claude flow rather than overriding your choice.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
STARTER_SOURCES = HERE.parent / "fetchers" / "news"   # shipped default news fetchers

DEFAULT_CONFIG = """\
# OpenPaper local engine — created by make_paper.py on first run.
# Edit freely; see skills/openpaper/references/config.example.yaml for all options.
engine: local
model: gemma4:e4b-it-q4_K_M     # any Ollama model; must be instruction-tuned (-it)
ollama_url: http://localhost:11434
location: "Oslo, Norway"
tagline: "All the news that fits the day you are about to have."
"""

DEFAULT_PREFERENCES = """\
# My Reading Preferences

## Interests
- Technology and AI (very interested)
- World news (interested)
- Science (some interest)

## Sources
- Hacker News
- BBC News

## Reading Profile
~14 articles, about 20 min. Written in Norwegian bokmål. Include weather for Oslo.

## Feedback
"""


def _config(data_dir: Path) -> dict:
    path = data_dir / "config.yaml"
    cfg = yaml.safe_load(path.read_text()) if path.exists() else {}
    cfg = cfg or {}
    if isinstance(cfg.get("local"), dict):
        cfg = {**cfg, **cfg["local"]}
    return cfg


def _bootstrap(data_dir: Path) -> None:
    """Make the local engine runnable on a fresh clone, with no Claude session.

    Idempotent — only fills in what's missing, never overwrites the user's files.
    Creates the data dirs, a `config.yaml` (engine: local), a starter
    `preferences.md`, and copies the shipped default news fetchers into
    `sources/`. To tailor sources and preferences to you, run the /openpaper
    skill once (Claude writes fetchers for the sites you actually read) or edit
    these files by hand.
    """
    for sub in ("sources", "incoming", "editions", "cache", "saved"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    config_path = data_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG)
        print(f"• created {config_path} (engine: local)", file=sys.stderr)

    prefs_path = data_dir / "preferences.md"
    if not prefs_path.exists():
        prefs_path.write_text(DEFAULT_PREFERENCES)
        print(f"• created {prefs_path} (starter interests — edit to taste)",
              file=sys.stderr)

    sources_dir = data_dir / "sources"
    existing = [p for p in sources_dir.glob("*.py") if not p.name.startswith("_")]
    if not existing and STARTER_SOURCES.is_dir():
        copied = []
        for fetcher in sorted(STARTER_SOURCES.glob("*.py")):
            shutil.copy2(fetcher, sources_dir / fetcher.name)
            copied.append(fetcher.stem)
        if copied:
            print(f"• installed starter news sources: {', '.join(copied)}",
                  file=sys.stderr)
            print("  → run the /openpaper skill to add sources tailored to you.",
                  file=sys.stderr)


def _run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(str(c) for c in cmd)}", file=sys.stderr)
    subprocess.run(cmd, check=True, cwd=HERE.parents[2])


def main() -> None:
    ap = argparse.ArgumentParser(description="OpenPaper agent-free pipeline (engine: local)")
    ap.add_argument("--data-dir", type=Path, default=Path(".openpaper"))
    ap.add_argument("--skip-fetch", action="store_true", help="reuse existing incoming/")
    ap.add_argument("--no-serve", action="store_true",
                    help="render only; don't start the preview server or open a browser")
    args = ap.parse_args()

    data_dir = args.data_dir

    # An existing config that opts into Claude wins — don't override the choice.
    # With no config yet, running this script *is* the opt-in to the local engine.
    config_path = data_dir / "config.yaml"
    if config_path.exists() and _config(data_dir).get("engine") != "local":
        sys.exit(
            "config.yaml has engine != 'local'. The default Claude flow is driven "
            "by the agent — just run the /openpaper skill and say \"make my paper\".\n"
            "To use the local model instead, set `engine: local` in "
            f"{config_path}."
        )

    _bootstrap(data_dir)

    edition = data_dir / "editions" / "draft.yaml"
    if not args.skip_fetch:
        _run(["uv", "run", str(HERE / "fetch_all.py"), "--data-dir", str(data_dir)])
    _run(["uv", "run", str(HERE / "curate.py"), "--data-dir", str(data_dir),
          "--output", str(edition)])

    render_cmd = ["uv", "run", str(HERE / "render.py"), "--data-dir", str(data_dir),
                  "--edition", str(edition)]
    local_templates = data_dir / "templates"        # supports a localised template copy
    if local_templates.exists():
        render_cmd += ["--templates-dir", str(local_templates)]
    _run(render_cmd)

    print("\n✓ Local edition complete.", file=sys.stderr)

    if args.no_serve:
        return

    # Mirror the Claude flow: serve the edition and open it in a browser.
    # serve.py blocks until Ctrl+C, so this is the last thing we do.
    serve_cmd = ["uv", "run", str(HERE / "serve.py"), "--data-dir", str(data_dir),
                 "--latest"]
    local_assets = local_templates / "assets"        # localised template ships its own assets
    if local_assets.exists():
        serve_cmd += ["--assets-dir", str(local_assets)]
    try:
        _run(serve_cmd)
    except KeyboardInterrupt:
        pass  # Ctrl+C reaches both the server and us; let it stop quietly


if __name__ == "__main__":
    main()
