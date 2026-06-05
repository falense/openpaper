# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""OpenPaper agent-free pipeline — fetch -> curate -> render, no Claude.

This is the entry point for `engine: local`. It chains the existing fetch and
render scripts around the local curation engine (curate.py), so a daily paper
can be produced from a plain shell with a local model and no Claude Code session.

    uv run make_paper.py --data-dir .openpaper

If `engine` is not `local` in config.yaml, it points you back to the Claude flow.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def _config(data_dir: Path) -> dict:
    path = data_dir / "config.yaml"
    cfg = yaml.safe_load(path.read_text()) if path.exists() else {}
    cfg = cfg or {}
    if isinstance(cfg.get("local"), dict):
        cfg = {**cfg, **cfg["local"]}
    return cfg


def _run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(str(c) for c in cmd)}", file=sys.stderr)
    subprocess.run(cmd, check=True, cwd=HERE.parents[2])


def main() -> None:
    ap = argparse.ArgumentParser(description="OpenPaper agent-free pipeline (engine: local)")
    ap.add_argument("--data-dir", type=Path, default=Path(".openpaper"))
    ap.add_argument("--skip-fetch", action="store_true", help="reuse existing incoming/")
    args = ap.parse_args()

    data_dir = args.data_dir
    cfg = _config(data_dir)
    if cfg.get("engine") != "local":
        sys.exit(
            "config.yaml has engine != 'local'. The default Claude flow is driven "
            "by the agent — just run the /openpaper skill and say \"make my paper\".\n"
            "To use the local model instead, set `engine: local` in "
            f"{data_dir}/config.yaml."
        )

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


if __name__ == "__main__":
    main()
