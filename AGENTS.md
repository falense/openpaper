# OpenPaper

## Docker Session Logs

The `docker-compose.yml` bind-mounts `~/.claude` into the container, so containerized runs (both the `interactive` service and the `test` service via `test_flow.py`) write session logs to the same project directory as host sessions: `~/.claude/projects/-home-sondre-Repositories-OpenPaper/`.

To identify container-originated sessions:

- **Agent SDK sessions** (`test_flow.py` dual-agent harness): first JSONL line has `"type":"queue-operation"` and messages use `"permissionMode":"bypassPermissions"`. The initial user message is the test script's prompt ("I want to set up OpenPaper…").
- **Interactive container sessions** (`docker-compose --profile interactive`): first line has `"type":"mode"` (like normal CLI sessions) but also use `"permissionMode":"bypassPermissions"`. Cross-reference with `~/.claude/sessions/*.json` where the session metadata may include a `name` field (e.g. `"docker-setup-openpaper"`).

Quick grep to list all container sessions:
```sh
grep -l 'bypassPermissions' ~/.claude/projects/-home-sondre-Repositories-OpenPaper/*.jsonl
```
