---
name: improve
description: >
  Create a structured GitHub issue from a session reflection or improvement idea
  using the gh CLI. Use this skill when the user asks to create an issue from a
  reflection, file an improvement, log a lesson learned, or says things like
  "make an issue for that", "track this", "file that as a bug", "create an
  improvement issue", or after running /reflect when the user agrees to capture
  findings. Also use when the user identifies something that should be fixed or
  improved and wants it tracked in GitHub.
---

# Improve

Turn session insights into a trackable GitHub issue. This skill bridges the gap
between "we noticed a problem" and "someone will fix it" — every issue it creates
links back to where the idea came from so future readers have full context.

## Step 1: Gather the improvement

Check the current conversation for a `/reflect` retrospective or other discussion
about what to improve. If there's a clear reflection with pain points, use that.

If there's no reflection in the conversation, ask the user what they'd like to
improve. A single sentence is enough to get started.

If a `/reflect` produced multiple pain points, ask the user which ones to turn
into issues (they may want one issue, several, or all of them).

## Step 2: Build the origin reference

Every issue must trace back to its origin so future readers understand the context.
Collect these details:

1. **Session ID** — run `echo $CLAUDE_SESSION_ID` to get the current session identifier
2. **Working directory** — the repo/project the session was working in
3. **Date** — today's date
4. **Trigger** — what specifically surfaced this (e.g., "reflection after refactoring the fetcher pipeline" or "user noticed flaky test during PR review")

## Step 3: Structure the issue

Draft the issue with this structure:

```
## Problem

What went wrong or what could be better. Be specific — name the files, tools,
or workflows involved.

## Context

Why this matters. What was the user trying to do when this came up.

## Suggested improvement

Concrete next steps. What should change and roughly how.

## Origin

- **Session:** `<session-id>`
- **Date:** <date>
- **Working directory:** `<path>`
- **Trigger:** <what surfaced this>
```

Write a concise title (under 70 characters) that captures the improvement, not
the session. Good: "Add retry logic to RSS fetcher timeout handling". Bad:
"Session reflection issue".

## Step 4: Confirm with the user

Show the draft title and body. Ask for confirmation before creating. The user
might want to adjust scope, wording, or labels.

## Step 5: Create the issue

Use the `gh` CLI to create the issue in the current repository:

```bash
gh issue create --title "<title>" --body "<body>"
```

Use a HEREDOC for the body to preserve formatting:

```bash
gh issue create --title "the title" --body "$(cat <<'EOF'
issue body here
EOF
)"
```

If the user wants labels, add `--label "label1,label2"`. Common useful labels:
`improvement`, `dx`, `bug`, `documentation`.

Report the issue URL back to the user when done.
