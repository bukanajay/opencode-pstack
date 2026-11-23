---
name: architect
description: "Sketch types, signatures, and module structure before code, then stay in the loop while implementation fills in. Use for /architect, 'architect this', 'design this', or non-trivial work where jumping to code would lock in the wrong shape."
compatibility: opencode
metadata:
  origin: "pstack"
  cursor-disable-model-invocation: "true"
---
> **OpenCode port note.** This skill was ported from Cursor's pstack. Where it names Cursor concepts (`Task` + `subagent_type`, `AskQuestion`, `run_in_background`, Cursor model slugs, `~/.cursor/rules/*.mdc`, `/loop`, Graphite/`gt`), translate per `OPENCODE.md` at the repo root.


# Architect

Before writing code, trace every system the change touches, then sketch two different shapes for it (types, signatures, module boundaries) and pick the one where each piece of state has one owner, each task has one way to do it, and callers need to know least. Redesign instead of patching if workarounds repeat.

For a large or contested design, run the **arena** skill instead of sketching alone.
