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

## Running an Optimization Loop

Use the test harness to iteratively improve skill files through ablation. The loop:

1. **Establish a baseline** — run with unmodified skill files
2. **Create variants** — copy and modify files under `overrides/<variant>/`
3. **Test in parallel** — run up to 3 variants simultaneously
4. **Compare** — pick the best, apply changes to the repo, commit
5. **Repeat** — use the committed state as the new baseline

### Example: testing a SKILL.md change

```bash
# 1. Run baseline
scripts/run_test.sh baseline --verbose &

# 2. Create a variant
mkdir -p overrides/v2-trim/skills/openpaper
cp skills/openpaper/SKILL.md overrides/v2-trim/skills/openpaper/SKILL.md
# edit the copy...

# 3. Test the variant
scripts/run_test.sh v2-trim --verbose &
wait

# 4. Compare
uv run scripts/compare_runs.py
```

### What to optimize for

| Metric | Target | Why |
|--------|--------|-----|
| `total_tool_errors` | 0 | Failed tool calls waste tokens and time |
| `total_duration_s` | Lower | Faster = cheaper |
| `total_tool_calls` | Lower (with same output quality) | Fewer calls = less exploration overhead |
| `verification_passed` | `true` | Must still produce a working paper |

Always visually inspect the generated HTML — metrics can pass while the paper looks wrong.

### What worked (from the initial optimization)

- **Trimming redundant content** (2320 → 663 lines, -71%): removed full example fetchers already encoded in `_base.py`, duplicate YAML examples, verbose walkthroughs
- **Rephrasing "Ask:" to "Say:"**: the word "Ask" triggers AskUserQuestion tool calls which fail in the test harness. Use "Say:" with explicit text instead.
- **Removing "confirm" / "ask for feedback"**: same trigger — use neutral phrasing like "Show the user" or `Say: "Here's your paper"`.

### What didn't work

- **Merging reference files**: combining `curation-guide.md` + `edition-schema.md` into one file made things worse — the agent expects the file structure described in SKILL.md.

### Noise and variance

Single runs have significant variance (0–4 errors on identical prompts). When evaluating small changes, run the same variant 2–3 times or only trust large deltas (e.g., 9 → 3 errors is real signal; 3 → 1 is noise).

## Scripts

| Script | Purpose |
|---|---|
| `scripts/test_flow.py` | Dual-agent coordinator, metrics collection, verification |
| `scripts/run_test.sh` | Shell wrapper — creates directories, launches Docker with per-run mounts |
| `scripts/compare_runs.py` | Reads `output/*/metrics.json`, prints comparison table |
