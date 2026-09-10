> **OpenCode port.** This is the opencode rewrite of Cursor's `setup-pstack`.
> It writes `.opencode/pstack-models.md`, which the other ported skills read
> as their per-role model override layer.

# Setup pstack (opencode)

Write `.opencode/pstack-models.md`, a checked-in-or-local rule that sets pstack's
model per role. The skills read it and fall back to running on the parent chat
model when a line is absent, so this is an override layer, not a requirement.

Upstream Cursor defaults (`grok-4.6-fast-xhigh`, `claude-fable-5-thinking-max`,
`gpt-5.6-sol-max`, `claude-opus-5-thinking-xhigh`) are Cursor model slugs and do
not resolve in opencode. Treat a missing line as `inherit-parent`, never as a
Cursor slug.

## Steps

### 1. Detect available models

Run `opencode models` (or read the user's `opencode.json` providers) to enumerate
the `provider/model-id` values usable as a `task` subagent `model` in this
session; that is the dependable source. If you cannot detect any, ask the user to
paste the IDs they have access to. Never write a real ID you have not confirmed
is available. The aliases `inherit-parent` and `auto` are always valid even
though they are not detected IDs.

### 2. Load current state

If `.opencode/pstack-models.md` exists in the project, read it and treat its
values as the current choices. Else, if `~/.config/opencode/pstack-models.md`
exists, read that. Otherwise start from all-`inherit-parent`.

### 3. Map and confirm

Show every role with its current model, marking any real ID not in the detected
set as needing a choice. Ask whether to accept as-is or change specific roles,
offering the detected models plus `inherit-parent` and `auto` (both mean: this
role runs on the parent chat model by omitting the `task` model override) as the
options. Prefer the `question` tool over free text. For panel roles (how critics,
arena runners, architect runners, interrogate reviewers) the value is a list, and
one subagent runs per entry, alias entries included, so the list length sets the
count. `arena cross-judge pool` is also a list, but Arena selects one value from
it whose model family differs from the parent's when possible. `swarm workers` is
the default model for every worker unless a race or comparison assigns another
model per arm.

### 4. Validate

Every real ID written must be in the detected set; `inherit-parent` and `auto`
always pass. If a chosen real ID is not available, stop and ask again. A rule
pointing at a model the user cannot use breaks every delegation that reads it.

### 5. Write the rule

Write `.opencode/pstack-models.md` (project-local; use
`~/.config/opencode/pstack-models.md` only if the user asks for a global
default). Overwrite the whole file so re-runs stay idempotent. Shape:

```
# pstack model configuration (opencode port). One line per role.
# Delete a line to run that role on the parent chat model.
# `inherit-parent` or `auto` as a value: omit the task model override.
# Alias entries in a panel list still count toward its fan-out.
# Values are opencode `provider/model-id` values (see `opencode models`).
feature, refactoring: inherit-parent
bug-fix: inherit-parent
perf-issue: inherit-parent
hillclimb: inherit-parent
judgment and prose: inherit-parent
hardest tasks: inherit-parent
how explorer: inherit-parent
how explainer: inherit-parent
how critics: inherit-parent
why investigators: inherit-parent
why synthesizer: inherit-parent
reflect tooling: inherit-parent
reflect judgment, divergent, synthesizer: inherit-parent
arena runners: inherit-parent
arena cross-judge pool: inherit-parent
swarm workers: inherit-parent
architect runners: inherit-parent
interrogate reviewers: inherit-parent
```

### 6. Confirm

Tell the user the rule was written and that it applies to new tasks. Re-running
this skill updates it.

### 7. Offer a verification skill (optional)

Check whether the project has a way to drive the real app for proof (a `verify-*`
skill, or an existing harness). If not, offer once: "want a project-local
verification skill, so agents can drive the app the way a user does and prove
changes work? I can generate one with /create-verification-skill." On yes, invoke
`/create-verification-skill` (resolves wherever this port is installed —
project `.opencode/` or global `~/.config/opencode/`). On no, move on without
pushing.
