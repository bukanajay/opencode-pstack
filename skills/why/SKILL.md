---
name: why
description: "Use for 'why does X work this way', 'why we picked Y', design rationale, regressions, postmortems, or data-backed thresholds. Returns a cited read on decisions and tradeoffs. Use how for runtime behavior."
compatibility: opencode
metadata:
  origin: "pstack"
  cursor-disable-model-invocation: "true"
---
> **OpenCode port note.** This skill was ported from Cursor's pstack. Where it names Cursor concepts (`Task` + `subagent_type`, `AskQuestion`, `run_in_background`, Cursor model slugs, `~/.cursor/rules/*.mdc`, `/loop`, Graphite/`gt`), translate per `OPENCODE.md` at the repo root.


# Why

Answer from the record, not the code: read the commits and PR discussions that introduced the target and each later change, and other sources if the trail is thin. Cite what the authors wrote, mark your own inferences as inferences, and say what the record does not answer.
