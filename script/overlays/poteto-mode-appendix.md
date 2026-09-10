## OpenCode adaptation

This skill was ported from Cursor's pstack without changing the playbooks above.
When a step names a Cursor concept, use the opencode equivalent:

- Subagents. `Task` with `subagent_type: "poteto-agent"` means invoke the
  `poteto-agent` subagent via opencode's `task` tool (or `@poteto-agent`).
  `subagent_type: "generalPurpose"` means opencode's `general` subagent
  (or `explore` for read-only exploration). `readonly: true` means use the
  `plan` agent or deny edit/bash permissions for that delegation.
- Background work. `run_in_background: true` means invoke via the `task` tool
  and continue; drain results before the report step (`swarm`, `arena`).
- Questions. Cursor's `AskQuestion` is opencode's `question` tool.
- Models. Slugs like `grok-4.6-fast-xhigh`, `claude-fable-5-thinking-max`,
  `gpt-5.6-sol-max`, and `opus` are Cursor names. Run `/setup-pstack`
  (the opencode port) to map each role to a model you have in opencode,
  recorded in `.opencode/pstack-models.md`. A role of `inherit-parent` or
  `auto` means omit the model override and run on the parent chat model.
- Persistent rules. `~/.cursor/rules/pstack-models.mdc` (`alwaysApply: true`)
  becomes `.opencode/pstack-models.md` (project) or the global equivalent,
  loaded as context. There is no `.mdc` mechanism in opencode.
- Long runs. Cursor's `/loop` does not exist in opencode. Re-invoke the same
  command until the playbook's predicate holds, keeping the decision trail
  (`show-me-your-work`) across turns.
- Shipping. Graphite (`gt`, merge-when-ready stacks) steps become a plain
  `git`/`gh` flow: verify each PR head independently, then merge in order.
  `control-cli` / `control-ui` / `deslop` (from `cursor-team-kit`) are not
  bundled here; skip those sub-steps or substitute your project's harness.
- Skill authoring. Cursor's built-in `/create-skill` is this repo's
  `authoring-a-skill` playbook plus opencode's `SKILL.md` frontmatter rules
  (`name` must match the directory, lowercase-hyphenated).
