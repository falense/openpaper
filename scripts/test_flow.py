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

Outputs:
  /output/metrics.json   — timing, rounds, tool call counts, errors
  /output/editions/      — copy of generated HTML editions
  /output/transcript.jsonl — full conversation log

Usage:
    uv run scripts/test_flow.py --verbose
    uv run scripts/test_flow.py --agent-model claude-sonnet-4-6

Environment:
    CLAUDE_CODE_OAUTH_TOKEN   OAuth token for both clients
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    ToolResultBlock,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / ".openpaper"
SKILL_MD = PROJECT_ROOT / "skills" / "openpaper" / "SKILL.md"
OUTPUT_DIR = Path("/output")

USER_SIM_PROMPT = """\
You are simulating a user setting up OpenPaper for the first time.
You are a software engineer in Oslo interested in AI and tech news.

Follow this script when the agent asks questions:

SOURCES: When asked about news sources, provide only:
- Hacker News (https://news.ycombinator.com)
That's it. Just the one source.

PREFERENCES: When asked about interests:
- AI and technology (very interested)
- ~10 articles per edition
- Location: Oslo, Norway
- No weather or markets needed, keep it simple

CONFIRMATIONS: When shown fetcher results or previews, confirm they look \
good unless they're clearly broken (empty results, errors, zero articles).

PAPER REVIEW: When shown the final paper, say it looks great.

COMPLETION: When the paper has been rendered and you've given feedback, \
include the exact string [DONE] at the end of your message.

Keep responses concise — one sentence max. Do NOT ask questions back. \
Just answer what was asked or confirm."""

DEFAULT_AGENT_MODEL = "claude-opus-4-6"
DEFAULT_USER_MODEL = "claude-sonnet-4-6"
MAX_TURNS_DEFAULT = 30


@dataclass
class TurnMetrics:
    turn: int
    role: str
    duration_s: float
    tool_calls: int = 0
    tool_errors: int = 0
    text_length: int = 0
    tools_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class TestMetrics:
    agent_model: str
    user_model: str
    started_at: str = ""
    finished_at: str = ""
    total_duration_s: float = 0.0
    total_rounds: int = 0
    total_tool_calls: int = 0
    total_tool_errors: int = 0
    completed: bool = False
    verification_passed: bool = False
    verification_failures: list[str] = field(default_factory=list)
    turns: list[dict] = field(default_factory=list)


def log(msg: str, verbose: bool = True) -> None:
    if verbose:
        print(f"[test] {msg}", flush=True)


def write_transcript(path: Path, turn: int, role: str, text: str, tools: list[str]) -> None:
    entry = {
        "turn": turn,
        "role": role,
        "text": text,
        "tools": tools,
        "timestamp": time.time(),
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def send_and_collect(
    client: ClaudeSDKClient,
    prompt: str,
    turn: int,
    role: str,
    transcript_path: Path,
    verbose: bool = False,
) -> tuple[str, TurnMetrics]:
    """Send a prompt and collect the full text response with metrics."""
    t0 = time.monotonic()
    await client.query(prompt)

    text_parts: list[str] = []
    tool_names: list[str] = []
    tool_errors: list[str] = []
    tool_call_count = 0
    tool_error_count = 0

    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_call_count += 1
                    tool_names.append(block.name)
        elif isinstance(msg, UserMessage):
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    if getattr(block, "is_error", False):
                        tool_error_count += 1
                        content = block.content if isinstance(block.content, str) else str(block.content)
                        tool_errors.append(content[:200])
        elif isinstance(msg, ResultMessage):
            break

    elapsed = time.monotonic() - t0
    full_text = "".join(text_parts)

    metrics = TurnMetrics(
        turn=turn,
        role=role,
        duration_s=round(elapsed, 1),
        tool_calls=tool_call_count,
        tool_errors=tool_error_count,
        text_length=len(full_text),
        tools_used=tool_names,
        errors=tool_errors,
    )

    write_transcript(transcript_path, turn, role, full_text, tool_names)

    if verbose:
        error_str = f" ({tool_error_count} errors)" if tool_error_count else ""
        preview = full_text[:150].replace("\n", " ")
        log(f"[{role} t={turn}] {elapsed:.0f}s, {tool_call_count} tools{error_str}: {preview}...")

    return full_text, metrics


def verify_setup() -> list[str]:
    """Check that the OpenPaper setup produced expected artifacts."""
    failures = []

    sources_dir = DATA_DIR / "sources"
    if not sources_dir.is_dir():
        failures.append("missing .openpaper/sources/ directory")
    else:
        fetchers = [f for f in sources_dir.glob("*.py") if f.name != "_base.py"]
        if len(fetchers) < 1:
            failures.append(
                f"expected >= 1 fetcher, found {len(fetchers)}: "
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


def export_artifacts(metrics: TestMetrics) -> None:
    """Copy editions and metrics to /output."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    editions_src = DATA_DIR / "editions"
    editions_dst = OUTPUT_DIR / "editions"
    if editions_src.is_dir():
        if editions_dst.exists():
            shutil.rmtree(editions_dst)
        shutil.copytree(editions_src, editions_dst)
        log(f"Exported {len(list(editions_dst.glob('*')))} edition files to /output/editions/")

    metrics_path = OUTPUT_DIR / "metrics.json"
    metrics_path.write_text(json.dumps(asdict(metrics), indent=2))
    log(f"Metrics written to /output/metrics.json")


async def run_test(
    agent_model: str,
    user_model: str,
    max_turns: int,
    verbose: bool,
) -> TestMetrics:
    """Run the dual-agent test. Returns metrics."""

    metrics = TestMetrics(
        agent_model=agent_model,
        user_model=user_model,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )

    transcript_path = OUTPUT_DIR / "transcript.jsonl"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    if transcript_path.exists():
        transcript_path.unlink()

    skill_instructions = SKILL_MD.read_text() if SKILL_MD.exists() else ""
    agent_system = (
        "You are running inside the OpenPaper project directory. "
        "Your job is to help the user set up OpenPaper from scratch. "
        "Follow the skill instructions below.\n\n"
        f"{skill_instructions}"
    )

    agent_options = ClaudeAgentOptions(
        system_prompt=agent_system,
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        model=agent_model,
        cwd=str(PROJECT_ROOT),
    )

    user_options = ClaudeAgentOptions(
        system_prompt=USER_SIM_PROMPT,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=1,
        model=user_model,
    )

    agent_client = ClaudeSDKClient(options=agent_options)
    user_client = ClaudeSDKClient(options=user_options)

    log(f"Connecting agent ({agent_model})...", verbose)
    await agent_client.connect()
    log(f"Connecting user simulator ({user_model})...", verbose)
    await user_client.connect()

    t0 = time.monotonic()

    try:
        initial_prompt = (
            "I want to set up OpenPaper. This is a fresh start — "
            "there's no .openpaper/ directory yet. Walk me through "
            "the full setup and make my first paper."
        )

        log("Turn 0: Sending initial prompt to agent", verbose)
        agent_response, turn_m = await send_and_collect(
            agent_client, initial_prompt, 0, "agent", transcript_path, verbose,
        )
        metrics.turns.append(asdict(turn_m))

        for turn in range(1, max_turns + 1):
            user_reply, user_m = await send_and_collect(
                user_client,
                f"The agent said:\n\n{agent_response}\n\nHow do you respond?",
                turn, "user", transcript_path, verbose,
            )
            metrics.turns.append(asdict(user_m))

            if "[DONE]" in user_reply:
                log(f"User simulator signaled completion at turn {turn}", True)
                metrics.total_rounds = turn
                metrics.completed = True
                break

            agent_response, agent_m = await send_and_collect(
                agent_client, user_reply, turn, "agent", transcript_path, verbose,
            )
            metrics.turns.append(asdict(agent_m))
        else:
            log(f"WARNING: Hit max turns ({max_turns}) without completion", True)
            metrics.total_rounds = max_turns

    finally:
        log("Disconnecting clients...", verbose)
        await user_client.disconnect()
        await agent_client.disconnect()

    metrics.total_duration_s = round(time.monotonic() - t0, 1)
    metrics.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    # Aggregate tool metrics
    for t in metrics.turns:
        metrics.total_tool_calls += t.get("tool_calls", 0)
        metrics.total_tool_errors += t.get("tool_errors", 0)

    # Verify
    log("Verifying artifacts...", True)
    failures = verify_setup()
    metrics.verification_failures = failures
    metrics.verification_passed = len(failures) == 0

    if failures:
        for f in failures:
            log(f"FAIL: {f}", True)
    else:
        log("PASS: All verification checks passed", True)

    # Summary
    log(
        f"Summary: {metrics.total_rounds} rounds, "
        f"{metrics.total_duration_s}s, "
        f"{metrics.total_tool_calls} tool calls "
        f"({metrics.total_tool_errors} errors)",
        True,
    )

    return metrics


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
        "--verbose",
        action="store_true",
        help="Print conversation progress",
    )
    args = parser.parse_args()

    metrics = asyncio.run(
        run_test(
            agent_model=args.agent_model,
            user_model=args.user_model,
            max_turns=args.max_turns,
            verbose=args.verbose,
        )
    )

    export_artifacts(metrics)

    sys.exit(0 if metrics.verification_passed else 1)


if __name__ == "__main__":
    main()
