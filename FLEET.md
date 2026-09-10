# FLEET.md — pstack agent visualization for opencode

The pstack author flaunts parallel-agent animations on X. In Cursor those
come from the native Task UI. Opencode has no equivalent widget, so this
port ships a file-level replacement with no opencode core changes: a live
fleet board read straight from opencode's session store.

## The two-pane setup (the X clip)

Pane 1 runs opencode. Pane 2 runs the board:

```sh
# pane 2, from anywhere in the project
python3 /path/to/opencode-pstack/script/pstack-fleet.py --watch
```

Then in pane 1:

```
/swarm <task>
```

### Inside the opencode IDE

The IDE has no custom-panel API, so the board cannot embed itself in
the IDE window. Two setups cover it with no extra tooling:

- Live view: open a VS Code integrated terminal beside the opencode
  chat and run the `--watch` command there. Same animation, inside the
  IDE window, one command to start.
- Zero commands: `/swarm`, `/arena`, and `/interrogate` already
  instruct the agent to paste the fleet board into its reply at fan-out
  and each drain, so the IDE chat shows the fleet on its own. If your
  install predates this, rerun `./install.sh` so the commands and the
  `scripts/pstack-fleet.py` copy update together.

Pane 2 animates: spinners on live sessions, elapsed and last-active
times, per-session todo progress, current in-progress todo, last tool
with status. Child sessions (subagents) nest under their parent, so a
swarm fan-out reads as a fleet and an arena as a candidate tree. Child
navigation still works in the TUI (`session_child_first`, cycle keys).

## Animated board (web)

The terminal board refreshes text. For real motion, serve the canvas
boards and open one in a browser tab:

```sh
python3 script/pstack-fleet-serve.py --open
```

With the default Mahabharata cast, `/` is the Chakravyuh: Drona's
seven-ring formation drawn flat on a dusk battlefield and manned by the
Kaurava host — foot soldiers, cavalry, and war elephants with howdahs
that wheel slowly around the rings. A single gate faces the camp. Your
live sessions are the Pandava side, each taking the field as a
traditional warrior in cast colors — dhoti, sash, ornaments, and a
mukut or war-helm — bearing the weapon of its personality. Arjun draws
his bow, Karna raises his sun-heart shield, Bhima shoulders his mace,
Krishna sounds the conch, old Bhishma aims bearded over his bow,
Draupadi holds living flame, Yudhishthira wears his crown, Vidura
counsels with an owl on his shoulder, Abhimanyu crosses twin swords.

Ring depth marks todo progress, so breaching the formation means
finishing the work. Warriors muster from the camp, thread the one open
spiral to their depth, and unwind back out the same gate when they go
idle — they never cross a ring wall. Click any warrior for its card. A
project switcher in the header moves the view between projects; it
defaults to the directory the server started in.

### Orbit, tilt, zoom

The battlefield is a camera you can fly around:

- **drag** — orbit a full 360 and tilt from a low angle to near
  top-down
- **scroll / pinch / the ± buttons** — zoom (warriors scale sub-linearly
  so they settle to human size beside the elephants as you close in,
  and stay a touch larger when zoomed out so you can pick them out)
- **⟲ or double-click** — reset the view
- **▶ 360°** (top-right) — hands-free auto-orbit; pauses while you
  interact or read a card

The sun rides the horizon and sets as you turn the camera away from it.

Custom casts get the cozy village at `/` instead: each agent is a
villager with its own hut, wandering while live and going home to rest
when idle. Force either view with `--theme war` or `--theme island`.
`/war`, `/island`, and `/graph` always serve their named view
directly. Custom characters may define a `token` emoji for the war
view; without one they march as ⚔️.

Same store, same manifest flags as the CLI (`--session`, `--fleet`,
`--cast`, `--no-cast` as flags or `?session=` style query params).
Stdlib only, nothing to install, binds to localhost.

## Snapshot into chat

The board is also pasteable. The parent agent runs this via bash at each
drain point and pastes the block so the transcript keeps the fleet state:

```sh
python3 script/pstack-fleet.py --once --plain --max 12
```

Use `--session <id>` to focus one parent and its children, `--all` to
watch every project, `--live-window <s>` to tune what counts as live
(default 60).

## Swarm and arena labels

Session titles do not carry worker names, so for `/swarm` and `/arena`
the parent writes a small manifest and points the board at it:

```json
{"fleet": "swarm-auth", "workers": [
  {"name": "worker-1", "slice": "login flow", "status": "running"},
  {"name": "worker-2", "slice": "refresh flow", "status": "done",
   "note": "PASS, 2 issues"}]}
```

```sh
python3 script/pstack-fleet.py --watch --fleet /tmp/swarm-auth.json
```

Statuses are `running`, `done`, `blocked`, or `failed`. The parent
updates the file with bash as workers report; the board merges fleet
labels above the live session tree.

## Cast (configurable characters)

Every agent on the board plays a character. The default cast comes from
the Mahabharata, with appearances matched to personality:
Krishna counsels in blue, Arjun executes in green, Karna outlasts in
gold, Bhishma guards in white, Draupadi questions in magenta,
Yudhishthira judges in cyan, Bhima lifts in red, Vidura watches from
afar in dim grey, and Abhimanyu breaches in bright red. Warriors march
under martial tokens: bow, shield, mace, conch, crossed swords.

The cast lives in `fleet/cast.json`:

```json
{"cast": [
  {"name": "Krishna", "title": "the Counselor", "symbol": "◈",
   "color": "blue", "token": "🐚", "bearing": "strategy before action",
   "suggested": "coordinator, cross-judge"},
  {"name": "Arjun", "title": "the Archer", "symbol": "➶",
   "color": "green", "token": "🏹", "bearing": "one target, one arrow",
   "suggested": "swarm workers"}]}
```

Make it yours: copy the file, rename characters, change `symbol` or
`color` (the seven bases plus `bright_*` variants, e.g. `bright_cyan`),
add entries. Then point the board at it:

```sh
python3 script/pstack-fleet.py --watch --cast ~/.config/opencode/fleet/cast.json
python3 script/pstack-fleet.py --once --plain --no-cast
```

Characters assign round-robin in display order. To pin one, set
`"character": "Karna"` on a manifest worker. A pinned name missing from
the cast is auto-generated: the board seeds an appearance from the name
itself, so it stays stable across frames, and picks a symbol and color
the current cast leaves free. `--no-cast` still renders everything
plain. Symbols survive `--plain`, so chat snapshots keep the cast.

## Optional log hook

`plugins/pstack-fleet.js` logs every `task` delegation via
`client.app.log`. It adds a timestamped trail, not visuals. Install:

```sh
# project or global
cp plugins/pstack-fleet.js .opencode/plugins/
cp plugins/pstack-fleet.js ~/.config/opencode/plugins/
```

Omit it and the board still works. The hook never throws by design.

## Honesty note

Opencode exposes no explicit running flag. A session counts as live when
its store row changed within the live window or its latest tool part is
pending or running. Idle means no recent activity, not finished. The
board labels the heuristic on every render. Requirements are Python 3.9+
stdlib only, plus read access to `~/.local/share/opencode/opencode.db`
(overridable with `--db`).
