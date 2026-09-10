#!/usr/bin/env python3
"""Re-port upstream pstack into this repo.

Usage:
    ./script/re-port.py --upstream /path/to/pstack-clone

What it does (idempotent):
  1. Copies upstream skills/, agents/, docs/, automations/ fresh.
  2. Normalizes skill frontmatter for opencode (name == directory,
     only name/description/compatibility/metadata, Cursor-only keys stashed
     under metadata.cursor-*).
  3. Applies local overlays from script/overlays/:
     - setup-pstack-body.md     (opencode rewrite of setup-pstack)
     - poteto-mode-appendix.md  (## OpenCode adaptation appendix)
  4. Regenerates agents/ (mode: subagent) and commands/ (slash wrappers).
  5. Verifies the result against opencode's loading rules.

Safe to re-run after `git pull` in the upstream clone. Review with
`git status` / `git diff` before committing.
"""
import argparse
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERLAYS = os.path.join(REPO, "script", "overlays")
SKILLS = os.path.join(REPO, "skills")
AGENTS_DST = os.path.join(REPO, "agents")
COMMANDS_DST = os.path.join(REPO, "commands")

CURSOR_KEYS = {"disable-model-invocation", "mode", "icon", "color", "reminder"}

# Skills whose bodies name Cursor-only concepts and need a pointer to OPENCODE.md
AFFECTED = {
    "poteto-mode", "how", "why", "swarm", "arena", "interrogate",
    "architect", "reflect", "setup-pstack", "automate-me", "no-comments",
    "recall", "teach", "figure-it-out", "blast-radius",
}

POINTER = (
    "> **OpenCode port note.** This skill was ported from Cursor's pstack. "
    "Where it names Cursor concepts (`Task` + `subagent_type`, `AskQuestion`, "
    "`run_in_background`, Cursor model slugs, `~/.cursor/rules/*.mdc`, `/loop`, "
    "Graphite/`gt`), translate per `OPENCODE.md` at the repo root.\n\n"
)


def split_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return None, text
    return m.group(1), m.group(2)


def parse_fm_lines(fm):
    """Return (name_value, description_value_verbatim, cursor_extras dict)."""
    name_val, desc_val = None, None
    extras = {}
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k == "name":
            name_val = v.strip("\"'")
        elif k == "description":
            desc_val = v  # keep verbatim (quoting intact)
        elif k in CURSOR_KEYS:
            extras[k] = v
    return name_val, desc_val, extras


def port_skills(appendix):
    fixed, pointed = 0, 0
    for dirname in sorted(os.listdir(SKILLS)):
        skill_md = os.path.join(SKILLS, dirname, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        text = open(skill_md, encoding="utf-8").read()
        fm, body = split_frontmatter(text)
        if fm is None:
            print(f"WARN: no frontmatter in {dirname}")
            continue
        name_val, desc_val, extras = parse_fm_lines(fm)
        if desc_val is None:
            print(f"WARN: no description in {dirname}")
            continue
        new_name = dirname  # opencode requires name == directory
        if name_val != new_name:
            print(f"FIX name: {dirname}: {name_val!r} -> {new_name!r}")
            fixed += 1
        lines = ["---", f"name: {new_name}", f"description: {desc_val}",
                 "compatibility: opencode", "metadata:"]
        lines.append('  origin: "pstack"')
        for k in sorted(extras):
            v = extras[k].strip("\"'")
            lines.append(f'  cursor-{k}: "{v}"')
        new_fm = "\n".join(lines) + "\n---\n"
        if dirname == "poteto-mode":
            body = body.rstrip("\n") + "\n\n" + appendix
        elif dirname == "setup-pstack":
            body = open(os.path.join(OVERLAYS, "setup-pstack-body.md"),
                        encoding="utf-8").read()
        elif dirname in AFFECTED:
            if "OpenCode port note" not in body:
                body = POINTER + body
                pointed += 1
        open(skill_md, "w", encoding="utf-8").write(new_fm + body)
    print(f"skills: fixed names={fixed}, pointers added={pointed}")


AGENT_NOTES = {
    "poteto-agent": (
        "\n> **OpenCode port note.** Invoke as `@poteto-agent` or via the `task` "
        "tool with the `poteto-agent` subagent. Read the `poteto-mode` skill with "
        "the `skill` tool (`skill({ name: \"poteto-mode\" })`) before any work.\n\n"
    ),
    "comment-sicko": (
        "\n> **OpenCode port note.** Invoke as `@comment-sicko` or via the `task` "
        "tool with the `comment-sicko` subagent, normally through the "
        "`no-comments` skill.\n\n"
    ),
}


def port_agents(agents_src):
    shutil.rmtree(AGENTS_DST, ignore_errors=True)
    os.makedirs(AGENTS_DST, exist_ok=True)
    for fname in sorted(os.listdir(agents_src)):
        if not fname.endswith(".md"):
            continue
        stem = fname[:-3]  # filename is the opencode agent name
        text = open(os.path.join(agents_src, fname), encoding="utf-8").read()
        fm, body = split_frontmatter(text)
        desc_val = None
        if fm is not None:
            _, desc_val, _ = parse_fm_lines(fm)
        if desc_val is None:
            print(f"WARN: no description in agent {fname}")
            desc_val = f"Ported pstack agent {stem}."
        new_fm = (
            "---\n"
            f"description: {desc_val}\n"
            "mode: subagent\n"
            "---\n"
        )
        note = AGENT_NOTES.get(stem, "")
        open(os.path.join(AGENTS_DST, fname), "w", encoding="utf-8").write(
            new_fm + note + body.lstrip("\n")
        )
        print(f"agent: {fname} -> mode=subagent")


# skill -> extra command guidance (beyond the generic skill-loader template)
COMMAND_GUIDANCE = {
    "poteto-mode": "Match the request to a playbook, copy its steps into a todo list verbatim, then work them.",
    "how": "The question text follows the command.",
    "why": "The question text follows the command. Use available evidence sources (git, docs, issues); skip MCP-only steps that have no opencode equivalent.",
    "architect": "Settle types, signatures, and module shape before implementing.",
    "arena": "Spawn parallel candidates via the task tool, pick a base, graft strengths.",
    "swarm": "Fan out parallel workers via the task tool, drain them, return one report.",
    "interrogate": "Run adversarial multi-model review of the diff under discussion.",
    "setup-pstack": "Detect models via `opencode models` and write `.opencode/pstack-models.md`.",
    "reflect": "Review the active session transcript and route learnings to skill edits.",
    "no-comments": "Spawn the comment-sicko subagent over the diff, fix accepted findings.",
    "tdd": "Only when the user asked for TDD or the bug has a cheap local test target.",
    "blast-radius": "Prove the one safety fact by running real code, not by asserting it.",
}


def first_sentence(desc_verbatim):
    d = desc_verbatim.strip().strip("\"'")
    d = re.sub(r"\s+", " ", d)
    m = re.match(r"(.+?[.!?])(\s|$)", d)
    s = (m.group(1) if m else d).strip()
    return s[:140]


def port_commands():
    shutil.rmtree(COMMANDS_DST, ignore_errors=True)
    os.makedirs(COMMANDS_DST, exist_ok=True)
    skills = {}
    for dirname in sorted(os.listdir(SKILLS)):
        skill_md = os.path.join(SKILLS, dirname, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        # principle-* skills are auto-applied by poteto-mode; no slash command
        if dirname.startswith("principle-"):
            continue
        fm, _ = split_frontmatter(open(skill_md, encoding="utf-8").read())
        _, desc_val, _ = parse_fm_lines(fm or "")
        skills[dirname] = desc_val or dirname
    for skill, desc in sorted(skills.items()):
        guidance = COMMAND_GUIDANCE.get(skill, "")
        body_lines = [
            f"Load the `{skill}` skill with the skill tool and follow it end to end.",
        ]
        if guidance:
            body_lines.append(guidance)
        body_lines.append("User request: $ARGUMENTS")
        cmd = (
            "---\n"
            f"description: {first_sentence(desc)}\n"
            "agent: build\n"
            "---\n" + "\n".join(body_lines) + "\n"
        )
        open(os.path.join(COMMANDS_DST, f"{skill}.md"),
             "w", encoding="utf-8").write(cmd)
    print(f"commands: wrote {len(skills)} wrappers")


def copy_docs_and_automations(src):
    for sub in ("docs", "automations"):
        s = os.path.join(src, sub)
        d = os.path.join(REPO, sub)
        if os.path.isdir(s):
            shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(s, d)
            print(f"copied {sub}/")


def verify():
    fails = 0
    names = {}
    pat = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    allowed = {"name", "description", "license", "compatibility", "metadata"}
    for d in sorted(os.listdir(SKILLS)):
        p = os.path.join(SKILLS, d, "SKILL.md")
        if not os.path.isfile(p):
            print(f"FAIL skill dir without SKILL.md: {d}")
            fails += 1
            continue
        fm, _ = split_frontmatter(open(p, encoding="utf-8").read())
        if fm is None:
            print(f"FAIL no frontmatter: {d}")
            fails += 1
            continue
        keys = [m.group(1) for m in re.finditer(r"^([A-Za-z0-9_-]+):", fm, re.M)]
        bad = [k for k in keys if k not in allowed]
        if bad:
            print(f"FAIL unknown fm keys {d}: {bad}")
            fails += 1
        nm = re.search(r"^name:\s*(.+?)\s*$", fm, re.M)
        ds = re.search(r"^description:\s*(.+?)\s*$", fm, re.M)
        name = nm.group(1).strip().strip("\"'") if nm else ""
        desc = ds.group(1).strip().strip("\"'") if ds else ""
        if name != d or not pat.match(name) or len(name) > 64:
            print(f"FAIL name {d!r} -> {name!r}")
            fails += 1
        if not 1 <= len(desc) <= 1024:
            print(f"FAIL desc len {d}: {len(desc)}")
            fails += 1
        names.setdefault(name, []).append(d)
    dupes = {k: v for k, v in names.items() if len(v) > 1}
    if dupes:
        print(f"FAIL dup skill names: {dupes}")
        fails += 1
    for f in sorted(os.listdir(AGENTS_DST)):
        fm, _ = split_frontmatter(
            open(os.path.join(AGENTS_DST, f), encoding="utf-8").read())
        fm = fm or ""
        if not (re.search(r"^description:\s*.+", fm, re.M)
                and re.search(r"^mode:\s*subagent", fm, re.M)):
            print(f"FAIL agent frontmatter {f}")
            fails += 1
    n = 0
    for f in sorted(os.listdir(COMMANDS_DST)):
        txt = open(os.path.join(COMMANDS_DST, f), encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", txt, re.S)
        if (not m or not re.search(r"^description:\s*.+", m.group(1), re.M)
                or "$ARGUMENTS" not in m.group(2)):
            print(f"FAIL command {f}")
            fails += 1
        n += 1
    # overlay markers survive a re-port
    poteto = open(os.path.join(SKILLS, "poteto-mode", "SKILL.md"),
                  encoding="utf-8").read()
    if "## OpenCode adaptation" not in poteto:
        print("FAIL poteto-mode appendix missing")
        fails += 1
    setup = open(os.path.join(SKILLS, "setup-pstack", "SKILL.md"),
                 encoding="utf-8").read()
    if "pstack-models.md" not in setup or "~/.cursor" in setup:
        print("FAIL setup-pstack overlay missing")
        fails += 1
    print(f"verify: {len(names)} skills, {n} commands, failures={fails}")
    return fails


def main():
    ap = argparse.ArgumentParser(description="Re-port upstream pstack.")
    ap.add_argument("--upstream", required=True,
                    help="path to a fresh pstack clone")
    args = ap.parse_args()
    for sub in ("skills", "agents"):
        if not os.path.isdir(os.path.join(args.upstream, sub)):
            sys.exit(f"error: {args.upstream} has no {sub}/ dir")
    appendix = open(os.path.join(OVERLAYS, "poteto-mode-appendix.md"),
                    encoding="utf-8").read()
    shutil.rmtree(SKILLS, ignore_errors=True)
    shutil.copytree(os.path.join(args.upstream, "skills"), SKILLS)
    port_skills(appendix)
    port_agents(os.path.join(args.upstream, "agents"))
    port_commands()
    copy_docs_and_automations(args.upstream)
    lic = os.path.join(args.upstream, "LICENSE")
    if os.path.isfile(lic):
        shutil.copyfile(lic, os.path.join(REPO, "LICENSE.upstream"))
    sys.exit(1 if verify() else 0)


if __name__ == "__main__":
    main()
