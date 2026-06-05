# Test Harness

Dual-agent end-to-end test harness for OpenPaper. Runs an AI agent through the full setup pipeline (add sources, set preferences, generate paper) while a second AI simulates a user following a scripted persona. Measures everything and compares runs.

## Quick Start

```bash
# Build the Docker image
docker compose build

# Run a baseline test
scripts/run_test.sh baseline --verbose

# Run a variant with a modified skill
cp -r skills/openpaper/SKILL.md overrides/v2-skill/skills/openpaper/SKILL.md
# edit the copy...
scripts/run_test.sh v2-skill --verbose

# Compare results
uv run scripts/compare_runs.py
```

## How It Works

Two Claude instances run in parallel inside Docker:

- **Agent under test** (Opus): Has full tool access and receives the SKILL.md instructions as its system prompt. Performs the complete OpenPaper setup.
- **User simulator** (Sonnet): No tools, follows a fixed script. Plays a software engineer in Oslo interested in AI/tech news who wants Hacker News as their only source.

The agent and user alternate turns until the user simulator emits `[DONE]` or `--max-turns` is reached. Every turn records timing, tool calls, errors, and text.

After the conversation ends, verification checks confirm the agent produced the expected artifacts:

- `.openpaper/sources/` has at least one fetcher (excluding `_base.py`)
- `.openpaper/preferences.md` exists and mentions Oslo
- `.openpaper/editions/` has at least one HTML file

## Testing Skill Variants

The override mechanism lets you swap any file in the repo for a specific test run. The `overrides/<run-id>/` directory mirrors the repo structure — the Docker entrypoint copies its contents over the repo at startup.

```
overrides/
  v2-skill/
    skills/openpaper/SKILL.md        # replaced skill instructions
  cached-run/
    skills/openpaper/scripts/
      fetch_all.py                   # replaced fetch script
```

To test a variant:

1. Create `overrides/<run-id>/` with the files you want to replace
2. Run `scripts/run_test.sh <run-id>`
3. Results land in `output/<run-id>/`

Leave the override directory empty for a baseline run.

## Parallel Runs

Runs are isolated by container name and output directory, so you can run them in parallel:

```bash
scripts/run_test.sh baseline --verbose &
scripts/run_test.sh v2-skill --verbose &
wait
```

## Output

Each run produces:

```
output/<run-id>/
  metrics.json         # timing, rounds, tool calls, errors, pass/fail
  transcript.jsonl     # turn-by-turn conversation log
  editions/            # copies of generated HTML newspapers
```

### metrics.json

```json
{
  "run_id": "baseline",
  "agent_model": "claude-opus-4-6",
  "user_model": "claude-sonnet-4-6",
  "total_duration_s": 674.1,
  "total_rounds": 2,
  "total_tool_calls": 68,
  "total_tool_errors": 9,
  "completed": true,
  "verification_passed": true,
  "turns": [...]
}
```

### Comparing Runs

```bash
uv run scripts/compare_runs.py
```

```
Run         Model            Duration  Rounds  Tools  Errors  Pass
baseline    claude-opus-4-6  674s      2       68     9       PASS
v2-skill    claude-opus-4-6  720s      2       72     5       PASS
```

## CLI Options

`scripts/run_test.sh` passes extra arguments to `test_flow.py`:

```
--run-id ID          Run identifier (default: "default")
--agent-model MODEL  Model for the agent (default: claude-opus-4-6)
--user-model MODEL   Model for the user sim (default: claude-sonnet-4-6)
--max-turns N        Max conversation turns (default: 30)
--verbose            Print turn-by-turn progress
```

Example with a different agent model:

```bash
scripts/run_test.sh sonnet-test --agent-model claude-sonnet-4-6 --verbose
```

## Docker Architecture

The image bakes in the repo via `COPY` for a clean git state. At runtime, only auth, cache, output, and overrides are mounted:

| Mount | Purpose |
|---|---|
| `~/.claude` | Session logs and auth tokens |
| `openpaper-cache` (volume) | Shared article cache across runs |
| `output/<run-id>` → `/output` | Per-run metrics, transcript, editions |
| `overrides/<run-id>` → `/overrides` | Skill variant files (read-only) |

The entrypoint (`entrypoint.sh`) fixes volume ownership, applies overrides via `cp -r /overrides/* .`, then drops to the host user with `gosu`.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/test_flow.py` | Dual-agent coordinator, metrics collection, verification |
| `scripts/run_test.sh` | Shell wrapper — creates directories, launches Docker with per-run mounts |
| `scripts/compare_runs.py` | Reads `output/*/metrics.json`, prints comparison table |
