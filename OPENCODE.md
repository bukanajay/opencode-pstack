# OPENCODE.md — Cursor → opencode translation for pstack skills

Skill bodies are upstream-verbatim. Wherever they name a Cursor concept, use
this table. `setup-pstack` (rewritten for opencode) and the
`## OpenCode adaptation` appendix in `poteto-mode` already assume it.

| Cursor (as written in skills) | Opencode (what to do) |
| --- | --- |
| `Task` tool with `subagent_type: "poteto-agent"` | `task` tool with the `poteto-agent` subagent, or `@poteto-agent` |
| `subagent_type: "generalPurpose"` | `general` subagent (multi-step work) or `explore` (read-only) |
| `subagent_type: "Comment Sicko"` | `comment-sicko` subagent, normally via `/no-comments` |
| `readonly: true` on a delegation | `plan` agent, or deny `edit`/`bash` for that delegation |
| `run_in_background: true` | Background `task` invocation; drain results before the report step |
| `AskQuestion` tool | `question` tool |
| Model slugs `grok-4.6-fast-xhigh`, `claude-fable-5-thinking-max`, `gpt-5.6-sol-max`, `opus`/`claude-opus-5` | Your opencode `provider/model-id` values per `.opencode/pstack-models.md` (`/setup-pstack`); `inherit-parent`/`auto` = omit the override |
| `~/.cursor/rules/pstack-models.mdc` (`alwaysApply`) | `.opencode/pstack-models.md` (project) or `~/.config/opencode/pstack-models.md` (global); plain markdown, no `.mdc` mechanism |
| `/loop` (run until predicate holds) | Re-invoke the same command until the playbook predicate holds; keep the `show-me-your-work` trail across turns |
| Cursor built-in `/babysit` | Pstack's `babysit` playbook (it supersedes the built-in by design) |
| `/create-skill` (Cursor built-in) | `authoring-a-skill` playbook + opencode `SKILL.md` rules (`name` == directory, lowercase-hyphen) |
| `deslop`, `control-cli`, `control-ui` (`cursor-team-kit` plugin) | Not bundled. Skip those sub-steps or substitute the project's harness |
| Graphite/`gt` stack + merge-when-ready (`shipping`, `autopilot-*`, `babysit`) | Plain `git`/`gh` flow: verify each PR head independently, merge in order |
| `/add-plugin pstack`, `.cursor-plugin/plugin.json` | This repo's `install.sh` (copies `skills/`, `agents/`, `commands/`) |
| `~/.cursor`, `.cursor/` paths (rules, automations) | `.opencode/` or `~/.config/opencode/`; benny pack under `automations/` still targets `.cursor/` and needs path edits before use |
| `mode: true`, `icon`, `color`, `reminder`, `disable-model-invocation` frontmatter | Cursor-only; stashed under `metadata.cursor-*` and ignored by opencode |
| `is_background: true` (agents) | Invoke via `task`; no frontmatter equivalent in opencode |

## Notes

- Opencode skill frontmatter accepts only `name`, `description`, `license`,
  `compatibility`, `metadata`. `name` must match the directory and match
  `^[a-z0-9]+(-[a-z0-9]+)*$`; `description` is 1–1024 chars. All skills in this
  repo satisfy that; it is checked by re-running the verification step below.
- Permissions: to let agents load skills and delegate, allow the `skill` and
  `task` tools (see `config/opencode.snippet.jsonc`).
- `poteto-mode`'s reply rules (short declarative sentences, no long-dash
  character, no mid-sentence colon, consumer-then-maintainer framing) apply
  unchanged in opencode.
