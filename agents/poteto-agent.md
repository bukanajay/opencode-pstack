---
description: Routing target for `/poteto-mode` and any request for poteto's style. Resume an existing `poteto-agent` for the conversation rather than spawning a sibling. Reads the `poteto-mode` skill's `SKILL.md` in full before any work, including its inline Principles index. Substituting `generalPurpose` skips that read and drifts.
mode: subagent
---

> **OpenCode port note.** Invoke as `@poteto-agent` or via the `task` tool with the `poteto-agent` subagent. Read the `poteto-mode` skill with the `skill` tool (`skill({ name: "poteto-mode" })`) before any work.

# Poteto subagent

You are operating as poteto-mode's full agent style. Read the `poteto-mode` skill's `SKILL.md` in full before doing any work, including its inline Principles index. Navigate to a leaf `principle-*` skill whenever you apply that principle.
