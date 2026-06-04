---
name: reflect
description: >
  Reflect on the current Claude Code session — review what went well, what didn't,
  and extract actionable takeaways. Use this skill when the user asks to reflect,
  review the session, do a retrospective, think about what happened, or says things
  like "how did that go", "what could we do better", "session review", "retro",
  or "what did we learn". Also use it proactively at the end of long or complex
  sessions when the user wraps up.
---

# Reflect

Review the current session and produce a structured retrospective. The goal is
honest self-assessment — not a polite summary, but a useful one that surfaces
patterns worth repeating and mistakes worth fixing.

## How to reflect

Walk through the conversation from the start. For each significant task or
interaction, consider:

- **Did it succeed?** Was the outcome what the user wanted?
- **Was the path efficient?** Or were there false starts, wrong assumptions,
  unnecessary retries?
- **Did any tools or approaches fail?** Why — wrong tool, bad assumptions,
  missing context?
- **Did the user have to correct course?** What was the misunderstanding?
- **What worked unusually well?** An approach worth reusing.

Be specific. Reference actual tasks, files, errors, and tool calls — not
vague generalities like "communication was good."

## Output format

Present the retrospective in this structure:

### What went well
Bullet list. Each item names a specific task or moment and why it went well.

### What didn't go well
Bullet list. Each item names what happened, what went wrong, and why. Be
direct — the point is to learn, not to soften.

### Takeaways
2-3 concrete lessons. Frame them as actionable guidance for future sessions
(e.g., "grep before assuming a function exists" not "could have been more
careful").

## After the retrospective

Once you've presented the reflection, offer:

> Want me to run `/improve` to turn any of these into a GitHub issue?

This lets the user capture pain points or ideas as trackable work items.
