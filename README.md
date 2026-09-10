# opencode-pstack

An [opencode](https://opencode.ai) port of [pstack](https://github.com/backnotprop/pstack)
(itself a mirror of `cursor/plugins/pstack`): skills and principles for rigorous
AI-assisted engineering. `pstack` turns the agent into a real engineering team;
this repo makes that usable from opencode.

> **Status.** Community port, not affiliated with Cursor, poteto, or opencode.
> Upstream source: `backnotprop/pstack` (MIT). See `LICENSE.upstream`.
> Skill bodies are kept verbatim except where Cursor-only concepts needed an
> opencode translation (see `OPENCODE.md`).

## Can pstack be used with opencode as-is?

No. Four blockers, all fixed by this port:

1. **Install.** Upstream installs via Cursor's `/add-plugin pstack` and its
   `.cursor-plugin/plugin.json` manifest. Opencode has no plugin-manifest
   installer for skill bundles; skills are discovered as `SKILL.md` files.
2. **Skill frontmatter.** Opencode requires `name` to be lowercase-hyphenated
   and equal to the directory name. Upstream `poteto-mode/SKILL.md` declares
   `name: Poteto Mode`, so the main entry point would not load.
3. **Slash commands.** In Cursor, skills are `/commands`. In opencode, `/slash`
   means `commands/*.md`; skills load on demand via the `skill` tool. This repo
   adds `commands/` wrappers so `/poteto-mode`, `/how`, etc. keep working.
4. **Runtime vocabulary.** Skill bodies name Cursor's `Task(subagent_type,
   readonly, run_in_background)`, the `AskQuestion` tool, Cursor model slugs,
   `~/.cursor/rules/*.mdc`, `/loop`, and Graphite/`gt`. `OPENCODE.md` maps each
   to its opencode equivalent, and `setup-pstack` is rewritten for opencode.

No opencode core changes are needed. The port is file-level only.

## Install

```sh
git clone https://github.com/<you>/opencode-pstack
cd opencode-pstack

./install.sh --global    # ~/.config/opencode/{skills,agents,commands}
./install.sh --project   # ./.opencode/{skills,agents,commands}
./install.sh --project /path/to/repo
```

Manual install works too: copy `skills/*`, `agents/*`, `commands/*` into the
matching `.opencode/` or `~/.config/opencode/` directories. Opencode also
discovers `.claude/skills/*` and `.agents/skills/*`, so those targets work.

Then run `/setup-pstack` once to map each role to a model you have in opencode
(recorded in `.opencode/pstack-models.md`).

## Usage

```
/setup-pstack        # once: map roles to your opencode models
/poteto-mode <task>  # default entry point for anything non-trivial
/how <question>      # subsystem walkthrough
/why <question>      # design rationale with evidence
/swarm <task>        # parallel workers, one report
/arena <task>        # parallel candidates, graft the best
/interrogate <diff>  # adversarial multi-model review
```

`poteto-mode` is sticky by convention: once entered it stays on across turns
until you opt out. (Cursor implements this with a `reminder`; in opencode the
skill text plus your command history carry it.)

## Layout

| Path | What |
| --- | --- |
| `skills/` | All upstream skills, opencode-compatible frontmatter. `poteto-mode` keeps its playbooks, references, and scripts verbatim plus an `## OpenCode adaptation` appendix. |
| `agents/` | `poteto-agent.md`, `comment-sicko.md` as opencode `mode: subagent` agents. Invoke with `@poteto-agent` / `@comment-sicko` or the `task` tool. |
| `commands/` | 23 slash wrappers (`poteto-mode`, `how`, `why`, …). `principle-*` skills ship skill-only; `poteto-mode` applies them. |
| `docs/`, `automations/` | Upstream guide and benny pack, verbatim. Benny targets `.cursor/`; see `OPENCODE.md` before using it with opencode. |
| `OPENCODE.md` | Cursor → opencode translation table. |
| `config/opencode.snippet.jsonc` | Optional `opencode.json` permissions snippet. |

| `script/re-port.py` + `script/overlays/` | Re-port script and opencode overlays (see below). |

## Updating from upstream

Skill bodies are verbatim so re-porting is mechanical:

```sh
git clone --depth 1 https://github.com/backnotprop/pstack /tmp/pstack-upstream
./script/re-port.py --upstream /tmp/pstack-upstream
git status  # review, then commit
```

The script re-copies upstream `skills/`, `agents/`, `docs/`, `automations/`,
re-applies the frontmatter normalization, regenerates `commands/`, layers the
overlays (`setup-pstack` rewrite, `poteto-mode` appendix), and verifies the
result against opencode's loading rules. If upstream adds a skill that names a
new Cursor-only concept, add its directory to `AFFECTED` in `script/re-port.py`
(or extend `OPENCODE.md`) before re-running.

## License

MIT for the port additions. Upstream files remain under their MIT license
(`LICENSE.upstream`). If you use "opencode" in this project's name publicly,
note it is not built by the opencode team.
