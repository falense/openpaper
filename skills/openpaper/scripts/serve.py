#!/usr/bin/env python3
"""Development preview server for OpenPaper editions."""
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import errno
import os
import sys
import webbrowser
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class OpenPaperHandler(SimpleHTTPRequestHandler):
    """Serves editions as the document root, with asset path rewriting."""

    def __init__(self, *args, editions_dir: Path, assets_dir: Path, **kwargs):
        self.editions_dir = editions_dir
        self.assets_dir = assets_dir
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str) -> str:
        # Strip query string and fragment
        path = path.split("?", 1)[0].split("#", 1)[0]

        # Route /assets/* to the plugin's template assets directory
        if path.startswith("/assets/"):
            rel = path[len("/assets/"):]
            return str(self.assets_dir / rel)

        # Everything else is served from the editions directory
        # Use SimpleHTTPRequestHandler's logic but rooted at editions_dir
        # We do this manually to avoid the os.getcwd() default
        from urllib.parse import unquote
        path = unquote(path)
        # Normalise and make relative
        path = path.lstrip("/")
        return str(self.editions_dir / path)

    def log_message(self, format, *args):
        # Log to stderr (default), keep it tidy
        sys.stderr.write(f"  {args[0]}\n")


def find_latest_html(editions_dir: Path) -> Path | None:
    """Return the most recently modified .html file in editions_dir."""
    html_files = list(editions_dir.rglob("*.html"))
    if not html_files:
        return None
    return max(html_files, key=lambda p: p.stat().st_mtime)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Development preview server for OpenPaper editions.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".openpaper"),
        help="path to .openpaper/ directory (default: .openpaper)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="port number (default: 8787)",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help="path to template assets directory (default: auto-detected relative to this script)",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="open the most recent edition in a browser",
    )
    args = parser.parse_args()

    # Resolve directories
    data_dir = args.data_dir.resolve()
    editions_dir = data_dir / "editions"

    if not editions_dir.is_dir():
        sys.stderr.write(f"Error: editions directory not found: {editions_dir}\n")
        sys.exit(1)

    # Locate template assets
    if args.assets_dir is not None:
        assets_dir = args.assets_dir.resolve()
    else:
        # Default: relative to this script at ../templates/assets/
        assets_dir = (Path(__file__).resolve().parent.parent / "templates" / "assets")

    if not assets_dir.is_dir():
        sys.stderr.write(f"Warning: assets directory not found: {assets_dir}\n")
        sys.stderr.write("  Template assets (magic.css, magic.js) will not be served.\n")

    # Build the handler with our directories baked in
    handler = partial(
        OpenPaperHandler,
        editions_dir=editions_dir,
        assets_dir=assets_dir,
    )

    port = args.port
    server = None
    for attempt in range(10):
        try:
            server = HTTPServer(("localhost", port), handler)
            break
        except OSError as e:
            # EADDRINUSE differs by platform (98 on Linux, 48 on macOS) — use the
            # symbolic value so the port fallback works everywhere.
            if e.errno == errno.EADDRINUSE and attempt < 9:
                port += 1
                continue
            raise
    url = f"http://localhost:{port}"

    sys.stderr.write(f"Serving editions from: {editions_dir}\n")
    sys.stderr.write(f"Assets from:           {assets_dir}\n")
    sys.stderr.write(f"Preview server:        {url}\n")

    # Open the latest edition if requested
    if args.latest:
        latest = find_latest_html(editions_dir)
        if latest:
            rel_path = latest.relative_to(editions_dir)
            edition_url = f"{url}/{rel_path}"
            sys.stderr.write(f"Opening latest:        {edition_url}\n")
            webbrowser.open(edition_url)
        else:
            sys.stderr.write("No .html files found in editions directory.\n")

    sys.stderr.write("\nPress Ctrl+C to stop.\n\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nStopped.\n")
        server.server_close()


if __name__ == "__main__":
    main()
