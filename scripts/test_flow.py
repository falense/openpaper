# /// script
# requires-python = ">=3.11"
# dependencies = ["claude-agent-sdk==0.1.37"]
# ///
"""Dual-agent end-to-end test of the OpenPaper pipeline.

Runs two Claude instances in parallel:
  - Opus agent (under test): has full tool access, runs the OpenPaper skill
  - Sonnet user simulator: follows a predefined script, answers agent questions

The simulated user guides the agent through first-run setup: adding sources,
setting preferences, and generating the first paper.

Usage:
    uv run --project . scripts/test_flow.py
    uv run --project . scripts/test_flow.py --clean --verbose
    uv run --project . scripts/test_flow.py --agent-model claude-sonnet-4-6

Environment:
    CLAUDE_CODE_OAUTH_TOKEN   OAuth token for both clients (required)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / ".openpaper"
SKILL_MD = PROJECT_ROOT / "skills" / "openpaper" / "SKILL.md"

USER_SIM_PROMPT = """\
You are simulating a user setting up OpenPaper for the first time.
You are a tech professional in Oslo who wants a morning news digest.

Follow this script when the agent asks questions:

SOURCES: When asked about news sources, provide:
- Hacker News (https://news.ycombinator.com)
- NRK (https://www.nrk.no)

PREFERENCES: When asked about interests:
- Technology and AI (very interested)
- Norwegian politics (some interest)
- ~14 articles per edition
- Location: Oslo, Norway
- Include weather and markets (Oslo Børs, USD/NOK, S&P 500)

CONFIRMATIONS: When shown fetcher results or previews, confirm they look \
good unless they're clearly broken (empty results, errors, zero articles).

PAPER REVIEW: When shown the final paper, give brief positive feedback \
with one small suggestion for improvement.

COMPLETION: When the paper has been rendered and you've given feedback, \
include the exact string [DONE] at the end of your message.

Keep responses concise and natural — one or two sentences max. You're busy.
Do NOT ask questions back. Just answer what was asked or confirm."""

DEFAULT_AGENT_MODEL = "claude-opus-4-6"
DEFAULT_USER_MODEL = "claude-sonnet-4-6"
MAX_TURNS_DEFAULT = 30


def log(msg: str, verbose: bool = True) -> None:
    if verbose:
        print(f"[test] {msg}", flush=True)


async def send_and_collect(
    client: ClaudeSDKClient,
    prompt: str,
    label: str = "",
    verbose: bool = False,
) -> str:
    """Send a prompt and collect the full text response."""
    await client.query(prompt)

    text_parts: list[str] = []
    tool_names: list[str] = []

    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_names.append(block.name)
        elif isinstance(msg, ResultMessage):
            break

    full_text = "".join(text_parts)
    if verbose and label:
        tools_summary = f" (tools: {', '.join(tool_names)})" if tool_names else ""
        preview = full_text[:200].replace("\n", " ")
        log(f"{label}: {preview}...{tools_summary}")

    return full_text


def verify_setup() -> list[str]:
    """Check that the OpenPaper setup produced expected artifacts."""
    failures = []

    sources_dir = DATA_DIR / "sources"
    if not sources_dir.is_dir():
        failures.append("missing .openpaper/sources/ directory")
    else:
        fetchers = [
            f for f in sources_dir.glob("*.py") if f.name != "_base.py"
        ]
        if len(fetchers) < 2:
            failures.append(
                f"expected >= 2 fetchers, found {len(fetchers)}: "
                f"{[f.name for f in fetchers]}"
            )

    prefs = DATA_DIR / "preferences.md"
    if not prefs.is_file():
        failures.append("missing .openpaper/preferences.md")
    elif "oslo" not in prefs.read_text().lower():
        failures.append("preferences.md does not mention Oslo")

    editions_dir = DATA_DIR / "editions"
    if not editions_dir.is_dir():
        failures.append("missing .openpaper/editions/ directory")
    else:
        html_files = list(editions_dir.glob("*.html"))
        if not html_files:
            failures.append("no HTML editions generated")

    return failures


async def run_test(
    agent_model: str,
    user_model: str,
    max_turns: int,
    verbose: bool,
) -> bool:
    """Run the dual-agent test. Returns True on success."""

    skill_instructions = SKILL_MD.read_text() if SKILL_MD.exists() else ""
    agent_system = (
        "You are running inside the OpenPaper project directory. "
        "Your job is to help the user set up OpenPaper from scratch. "
        "Follow the skill instructions below.\n\n"
        f"{skill_instructions}"
    )

    agent_options = ClaudeAgentOptions(
        system_prompt=agent_system,
        permission_mode="dangerouslySkipPermissions",
        max_turns=max_turns,
        model=agent_model,
        cwd=str(PROJECT_ROOT),
    )

    user_options = ClaudeAgentOptions(
        system_prompt=USER_SIM_PROMPT,
        allowed_tools=[],
        permission_mode="dangerouslySkipPermissions",
        max_turns=1,
        model=user_model,
    )

    agent_client = ClaudeSDKClient(options=agent_options)
    user_client = ClaudeSDKClient(options=user_options)

    log(f"Connecting agent ({agent_model})...", verbose)
    await agent_client.connect()
    log(f"Connecting user simulator ({user_model})...", verbose)
    await user_client.connect()

    try:
        initial_prompt = (
            "I want to set up OpenPaper. This is a fresh start — "
            "there's no .openpaper/ directory yet. Walk me through "
            "the full setup and make my first paper."
        )

        log("Turn 0: Sending initial prompt to agent", verbose)
        t0 = time.monotonic()
        agent_response = await send_and_collect(
            agent_client, initial_prompt, "agent", verbose
        )

        for turn in range(1, max_turns + 1):
            log(f"Turn {turn}: Agent responded, feeding to user sim", verbose)
            user_reply = await send_and_collect(
                user_client,
                f"The agent said:\n\n{agent_response}\n\nHow do you respond?",
                "user",
                verbose,
            )

            if "[DONE]" in user_reply:
                log(f"User simulator signaled completion at turn {turn}", verbose)
                break

            log(f"Turn {turn}: User replied, feeding back to agent", verbose)
            agent_response = await send_and_collect(
                agent_client, user_reply, "agent", verbose
            )
        else:
            log(f"WARNING: Hit max turns ({max_turns}) without completion", True)

        elapsed = time.monotonic() - t0
        log(f"Conversation finished in {elapsed:.0f}s", True)

    finally:
        log("Disconnecting clients...", verbose)
        await user_client.disconnect()
        await agent_client.disconnect()

    log("Verifying artifacts...", True)
    failures = verify_setup()

    if failures:
        for f in failures:
            log(f"FAIL: {f}", True)
        return False

    log("PASS: All verification checks passed", True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--agent-model",
        default=DEFAULT_AGENT_MODEL,
        help=f"Model for the agent under test (default: {DEFAULT_AGENT_MODEL})",
    )
    parser.add_argument(
        "--user-model",
        default=DEFAULT_USER_MODEL,
        help=f"Model for the user simulator (default: {DEFAULT_USER_MODEL})",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=MAX_TURNS_DEFAULT,
        help=f"Maximum conversation turns (default: {MAX_TURNS_DEFAULT})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe .openpaper/ before running (fresh start)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full conversation transcript",
    )
    args = parser.parse_args()

    if args.clean and DATA_DIR.exists():
        print(f"[test] Cleaning {DATA_DIR}", flush=True)
        shutil.rmtree(DATA_DIR)

    success = asyncio.run(
        run_test(
            agent_model=args.agent_model,
            user_model=args.user_model,
            max_turns=args.max_turns,
            verbose=args.verbose,
        )
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
